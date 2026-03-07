# 原始代码来自 TWanSigmaGraph (https://github.com/Temult/TWanSigmaGraph)
# 原作者: Temult
# 许可证: MIT License
# 
# 修改说明:
# - 修复了曲线调整无效的问题
#
# 修改者: [supElement]
# 修改日期: 2026-02-28

# Import necessary libraries
import json
import torch
import math # Import math for isnan
import re   # 新增正则库用于后备兼容解析

class Element_SigmaGraph:
    """
    A ComfyUI node that generates a sigma schedule tensor based on user-defined
    points edited via a custom graph widget in the UI. It also outputs the
    number of steps used. The schedule typically decreases from high sigma
    (noise) to low sigma.
    """
    # Define a small epsilon for floating point comparisons
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
            
            # 【修改点 1】：新增可选的 latent 输入。这在代码逻辑中作为占位符，但能强制 ComfyUI 保持正确的执行顺序和显存回收策略。
            "optional": {
                "latent": ("LATENT",),
            }    
        }

    RETURN_TYPES = ("SIGMAS", "INT",)
    RETURN_NAMES = ("sigmas", "steps",)
    FUNCTION = "calculate_sigmas"
    CATEGORY = "Element_easy/custom_SIGMAS"

    def _validate_and_clean_points(self, points_data_str):
        """ Parses, validates, and cleans the points data. """
        points =[]
        default_points_list =[{"x": 0.0, "y": 1.0}, {"x": 1.0, "y": 0.0}]
        
        try:
            points_data = json.loads(points_data_str)
            if not isinstance(points_data, list):
                raise ValueError("Graph data is not a list.")
        except json.JSONDecodeError:
            # 兼容旧工作流：当JS传过来的是逗号分隔的纯文本时，手动将纯文本转换回节点列表
            try:
                nums_str = re.findall(r'-?\d+\.?\d*', points_data_str)
                nums = [float(n) for n in nums_str]
                if not nums:
                    raise ValueError("No valid numbers found in string.")
                if len(nums) == 1:
                    points_data = [{"x": 0.0, "y": nums[0]}, {"x": 1.0, "y": 0.0}]
                else:
                    points_data =[{"x": float(i) / (len(nums) - 1), "y": float(y)} for i, y in enumerate(nums)]
            except Exception as e:
                print(f"[Element_SigmaGraph Warning] Invalid graph_data input format: {e}. Using default points.")
                return default_points_list
        except (ValueError, TypeError) as e:
            print(f"[Element_SigmaGraph Warning] Invalid graph_data input: {e}. Using default points.")
            return default_points_list

        # Filter for valid point structure and numeric types
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

        # Ensure boundary points exist using a tolerance
        has_start = any(abs(p['x'] - 0.0) < self.EPSILON for p in points)
        has_end = any(abs(p['x'] - 1.0) < self.EPSILON for p in points)

        if not has_start:
            start_y = min(points, key=lambda p: abs(p['x'] - 0.0))['y'] if points else 1.0
            points.append({"x": 0.0, "y": start_y})
        if not has_end:
            end_y = min(points, key=lambda p: abs(p['x'] - 1.0))['y'] if points else 0.0
            points.append({"x": 1.0, "y": end_y})

        # Sort points by x-coordinate
        points.sort(key=lambda p: p["x"])

        # Remove duplicate points based on x-coordinate with tolerance
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

    # 【修改点 2】：参数中接收可选的 latent=None
    
    def calculate_sigmas(self, steps, graph_data, latent=None):
        """
        Calculates a sigma schedule tensor and returns it along with the steps.
        """
        steps = max(1, int(steps))
        points = self._validate_and_clean_points(graph_data)
        
        # 【1】：N 步采样需要 N+1 个 sigma 节点来构成 N 个区间
        num_sigmas_to_generate = steps + 1

        # --- Perform Interpolation ---
        sigma_values =[]
        current_point_idx = 0

        # 【2】：移除了 if steps == 1 的特判，统一循环逻辑
        for i in range(num_sigmas_to_generate):
            # 【3】：分母改为 steps，由于步数至少为1，不会出现除零错误
            # i 的取值范围是 0 到 steps，所以 step_progress 刚好从 0.0 平滑过渡到 1.0
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
                
            # 【修改点 3】：移除 0.001 限制，允许曲线真正到达 0.0
            
            sigma_values.append(max(0.0, sigma))

        sigmas_tensor = torch.tensor(sigma_values, dtype=torch.float32)
        
        # 【修改点 4】：显式指定 device="cpu"，与 ComfyUI 原生 Scheduler 的输出设备保持完全一致
        sigmas_tensor = torch.tensor(sigma_values, dtype=torch.float32, device="cpu")
        
        # 返回长度为 N+1 的 tensor，以及整数 N
        return (sigmas_tensor, steps,)

NODE_CLASS_MAPPINGS = { "Element_SigmaGraph": Element_SigmaGraph }
NODE_DISPLAY_NAME_MAPPINGS = { "Element_SigmaGraph": "Sigma Schedule Graph" }
