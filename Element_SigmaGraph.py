# 原始代码来自 TWanSigmaGraph (https://github.com/Temult/TWanSigmaGraph)
# 原作者: Temult
# 许可证: MIT License
# 
# 修改说明:
# - 修复了曲线调整无效的问题
# - 【新增】加入 custom_sigmas 输入端，支持接收外部传入数列并自动更新 UI
#
# 修改者: [supElement]
# 修改日期: 2026-02-28

import os
import json
import torch
import math 
import re   
from server import PromptServer 
from aiohttp import web 

class Element_SigmaGraph:
    EPSILON = 1e-6

    @classmethod
    def INPUT_TYPES(cls):
        default_points = json.dumps([
            {"x": 0.0, "y": 1.0},
            {"x": 0.5, "y": 0.5},
            {"x": 1.0, "y": 0.0}
        ])
        return {
            "required": {
                "steps": ("INT", {
                    "default": 20, "min": 1, "max": 1000,
                }),
                "graph_data": ("STRING", {
                    "default": default_points,
                    "multiline": True,
                }),
            },
            "optional": {
                "custom_sigmas": ("SIGMAS",), 
                "latent": ("LATENT",),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",  
            }
        }

    RETURN_TYPES = ("SIGMAS", "INT",)
    RETURN_NAMES = ("sigmas", "steps",)
    FUNCTION = "calculate_sigmas"
    CATEGORY = "Element_easy/custom_SIGMAS"
    
    OUTPUT_NODE = True

    def _validate_and_clean_points(self, points_data_str):
        """ Parses, validates, and cleans the points data. """
        points =[]
        default_points_list =[{"x": 0.0, "y": 1.0}, {"x": 1.0, "y": 0.0}]
        
        try:
            points_data = json.loads(points_data_str)
            if not isinstance(points_data, list):
                raise ValueError("Graph data is not a list.")
        except json.JSONDecodeError:
            try:
                nums_str = re.findall(r'-?\d+\.?\d*', points_data_str)
                nums = [float(n) for n in nums_str]
                if not nums:
                    raise ValueError("No valid numbers found in string.")
                if len(nums) == 1:
                    points_data =[{"x": 0.0, "y": nums[0]}, {"x": 1.0, "y": 0.0}]
                else:
                    points_data =[{"x": float(i) / (len(nums) - 1), "y": float(y)} for i, y in enumerate(nums)]
            except Exception as e:
                print(f"[Element_SigmaGraph Warning] Invalid graph_data input format: {e}. Using default points.")
                return default_points_list
        except (ValueError, TypeError) as e:
            print(f"[Element_SigmaGraph Warning] Invalid graph_data input: {e}. Using default points.")
            return default_points_list

        try:
            valid_points =[]
            for p in points_data:
                if isinstance(p, dict) and 'x' in p and 'y' in p and \
                   isinstance(p['x'], (int, float)) and not math.isnan(p['x']) and not math.isinf(p['x']) and \
                   isinstance(p['y'], (int, float)) and not math.isnan(p['y']) and not math.isinf(p['y']):
                    valid_points.append({"x": float(p['x']), "y": float(p['y'])})
                else:
                    print(f"[Element_SigmaGraph Warning] Ignoring invalid point data: {p}")

            points = valid_points
            if len(points) != len(points_data):
                 print("[Element_SigmaGraph Warning] Some points in graph_data were invalid and ignored.")

        except Exception as e:
            print(f"[Element_SigmaGraph Warning] Error processing points: {e}. Using default.")
            return default_points_list

        if not points:
             return default_points_list

        has_start = any(abs(p['x'] - 0.0) < self.EPSILON for p in points)
        has_end = any(abs(p['x'] - 1.0) < self.EPSILON for p in points)

        if not has_start:
            start_y = min(points, key=lambda p: abs(p['x'] - 0.0))['y'] if points else 1.0
            points.append({"x": 0.0, "y": start_y})
        if not has_end:
            end_y = min(points, key=lambda p: abs(p['x'] - 1.0))['y'] if points else 0.0
            points.append({"x": 1.0, "y": end_y})

        points.sort(key=lambda p: p["x"])

        unique_points = []
        if points:
            unique_points.append(points[0])
            last_x = points[0]['x']
            for i in range(1, len(points)):
                if abs(points[i]["x"] - last_x) > self.EPSILON:
                    unique_points.append(points[i])
                    last_x = points[i]['x']

        if len(unique_points) < 2:
             return default_points_list

        return unique_points

    def calculate_sigmas(self, steps, graph_data, custom_sigmas=None, latent=None, unique_id=None):
    
        if custom_sigmas is not None:
            
            if isinstance(custom_sigmas, torch.Tensor):
                sig_list = custom_sigmas.squeeze().tolist()
            elif isinstance(custom_sigmas, list):
                sig_list = custom_sigmas
            else:
                sig_list = [custom_sigmas]
                
            if not isinstance(sig_list, list):
                sig_list = [sig_list]

            num_sigmas = len(sig_list)
            if num_sigmas >= 2:
                new_steps = num_sigmas - 1
                points =[{"x": float(i) / new_steps, "y": float(v)} for i, v in enumerate(sig_list)]
                node_id_str = unique_id[0] if isinstance(unique_id, list) else str(unique_id)
                
                if unique_id is not None:
                    PromptServer.instance.send_sync("element_sigma_graph_update", {
                        "node_id": node_id_str,
                        "points": points,
                        "steps": new_steps
                    })
                
                if isinstance(custom_sigmas, torch.Tensor):
                    sigmas_tensor = custom_sigmas.clone().detach().to("cpu", dtype=torch.float32)
                else:
                    sigmas_tensor = torch.tensor(sig_list, dtype=torch.float32, device="cpu")
                    
                return (sigmas_tensor, new_steps,)
            else:
                print("[Element_SigmaGraph Warning] custom_sigmas 输入的数据过短，已回退至界面曲线数据。")

        steps = max(1, int(steps))
        points = self._validate_and_clean_points(graph_data)
        num_sigmas_to_generate = steps + 1

        sigma_values =[]
        current_point_idx = 0

        for i in range(num_sigmas_to_generate):
            step_progress = i / steps
            step_progress = min(1.0, max(0.0, step_progress))

            while (current_point_idx < len(points) - 2 and
                   points[current_point_idx + 1]["x"] < step_progress - self.EPSILON):
                current_point_idx += 1

            p1 = points[current_point_idx]
            p2 = points[min(current_point_idx + 1, len(points) - 1)]

            x_diff = p2["x"] - p1["x"]
            sigma = 0.0

            if x_diff <= self.EPSILON:
                sigma = p2["y"] if abs(step_progress - p2["x"]) < abs(step_progress - p1["x"]) else p1["y"]
            else:
                clamped_progress = max(p1["x"], min(p2["x"], step_progress))
                ratio = (clamped_progress - p1["x"]) / x_diff
                ratio = max(0.0, min(1.0, ratio))
                sigma = p1["y"] + ratio * (p2["y"] - p1["y"])
                
            sigma_values.append(max(0.0, sigma))
            
        sigmas_tensor = torch.tensor(sigma_values, dtype=torch.float32, device="cpu")
        return (sigmas_tensor, steps,)

NODE_CLASS_MAPPINGS = { "Element_SigmaGraph": Element_SigmaGraph }
NODE_DISPLAY_NAME_MAPPINGS = { "Element_SigmaGraph": "Sigma Schedule Graph" }

# ==========================================
# 预设文件存储 API (与前端交互)
# ==========================================

base_dir = os.path.dirname(os.path.abspath(__file__))
presets_dir = os.path.join(base_dir, "presets")
presets_file = os.path.join(presets_dir, "Sigma_presets.json")

if not os.path.exists(presets_dir):
    os.makedirs(presets_dir, exist_ok=True)

@PromptServer.instance.routes.get("/element_easy/sigma_presets")
async def get_sigma_presets(request):
    if os.path.exists(presets_file):
        try:
            with open(presets_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return web.json_response(data)
        except Exception as e:
            print(f"[Element_SigmaGraph] 读取预设文件失败: {e}")
    return web.json_response([])  

@PromptServer.instance.routes.post("/element_easy/sigma_presets")
async def save_sigma_presets(request):
    try:
        data = await request.json()
        with open(presets_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        return web.json_response({"status": "success"})
    except Exception as e:
        print(f"[Element_SigmaGraph] 保存预设文件失败: {e}")
        return web.json_response({"status": "error", "message": str(e)}, status=500)
        
