# 原始代码来自 TWanSigmaGraph (https://github.com/Temult/TWanSigmaGraph)
# 原作者: Temult
# 许可证: MIT License
# 
# 修改说明:
# - 【更新】实现在鼠标点击曲线的位置增减控制点，其它控制点位置和曲率最大限度保持不变（双击添加，右键删除）
# - 【更新】改为使用单独json文件存取预设
# - 【新增】加入 custom_sigmas, latent 可选输入端, 添加节点可单独执行功能
# - 【修复】y值限制在[0,1]范围内，修复浮点精度问题
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
        points = []
        default_points_list = [{"x": 0.0, "y": 1.0}, {"x": 1.0, "y": 0.0}]
        
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
                    points_data = [{"x": 0.0, "y": nums[0]}, {"x": 1.0, "y": 0.0}]
                else:
                    points_data = [{"x": float(i) / (len(nums) - 1), "y": float(y)} for i, y in enumerate(nums)]
            except Exception as e:
                print(f"[Element_SigmaGraph Warning] Invalid graph_data input format: {e}. Using default points.")
                return default_points_list
        except (ValueError, TypeError) as e:
            print(f"[Element_SigmaGraph Warning] Invalid graph_data input: {e}. Using default points.")
            return default_points_list

        try:
            valid_points = []
            for p in points_data:
                if isinstance(p, dict) and 'x' in p and 'y' in p and \
                   isinstance(p['x'], (int, float)) and not math.isnan(p['x']) and not math.isinf(p['x']) and \
                   isinstance(p['y'], (int, float)) and not math.isnan(p['y']) and not math.isinf(p['y']):
                    # 限制 y 在 [0, 1] 范围内
                    y_clamped = max(0.0, min(1.0, float(p['y'])))
                    valid_points.append({"x": float(p['x']), "y": y_clamped})
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
            start_y = max(0.0, min(1.0, start_y))
            points.append({"x": 0.0, "y": start_y})
        if not has_end:
            end_y = min(points, key=lambda p: abs(p['x'] - 1.0))['y'] if points else 0.0
            end_y = max(0.0, min(1.0, end_y))
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

    def _linear_interpolate(self, x_query, points):
        """
        线性插值：在两点之间进行线性插值
        """
        if not points or len(points) < 2:
            return 0.0
        
        # 找到对应的区间
        for i in range(len(points) - 1):
            p1 = points[i]
            p2 = points[i + 1]
            
            if p1['x'] <= x_query <= p2['x'] or \
               abs(x_query - p1['x']) < self.EPSILON or \
               abs(x_query - p2['x']) < self.EPSILON:
                # 线性插值公式: y = y1 + (y2 - y1) * (x - x1) / (x2 - x1)
                if abs(p2['x'] - p1['x']) < self.EPSILON:
                    return max(0.0, min(1.0, p1['y']))
                t = (x_query - p1['x']) / (p2['x'] - p1['x'])
                y = p1['y'] + t * (p2['y'] - p1['y'])
                return max(0.0, min(1.0, y))
        
        # 边界外使用端点值
        if x_query < points[0]['x']:
            return max(0.0, min(1.0, points[0]['y']))
        else:
            return max(0.0, min(1.0, points[-1]['y']))

    def _format_sigma_value(self, val):
        """
        格式化 sigma 值，避免科学计数法，并处理浮点精度误差
        """
        if abs(val) < 1e-10:
            val = 0.0
        val = max(0.0, min(1.0, val))
        return round(val, 10)

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
                points = [{"x": float(i) / new_steps, "y": self._format_sigma_value(float(v))} for i, v in enumerate(sig_list)]
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
                    formatted_list = [self._format_sigma_value(v) for v in sig_list]
                    sigmas_tensor = torch.tensor(formatted_list, dtype=torch.float32, device="cpu")
                    
                return (sigmas_tensor, new_steps,)
            else:
                print("[Element_SigmaGraph Warning] custom_sigmas 输入的数据过短，已回退至界面曲线数据。")

        steps = max(1, int(steps))
        points = self._validate_and_clean_points(graph_data)
        num_sigmas_to_generate = steps + 1

        # 使用线性插值
        sigma_values = []
        for i in range(num_sigmas_to_generate):
            step_progress = i / steps
            step_progress = min(1.0, max(0.0, step_progress))
            
            sigma = self._linear_interpolate(step_progress, points)
            sigma_formatted = self._format_sigma_value(sigma)
            sigma_values.append(sigma_formatted)
            
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
