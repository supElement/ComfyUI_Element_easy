# 原始代码来自 TWanSigmaGraph (https://github.com/Temult/TWanSigmaGraph)
# 原作者: Temult
# 许可证: MIT License
# 
# 修改说明:
# - 【重大更新】实现三次样条插值，曲线真正平滑且经过所有控制点
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

class Element_SigmaGraph_Curve:
    EPSILON = 1e-6

    @classmethod
    def INPUT_TYPES(cls):
        default_points = json.dumps({
            "points": [{"x": 0.0, "y": 1.0}, {"x": 1.0, "y": 0.0}],
            "mode": "curve"
        })
        return {
            "required": {
                "steps": ("INT", {
                    "default": 20, "min": 1, "max": 1000,
                }),
                "graph_data": ("STRING", {
                    "default": default_points,
                    "multiline": True,
                }),
                "max_value": ("FLOAT", {  
                    "default": 1.0,
                    "min": 0.01,
                    "max": 1000.0,
                    "step": 0.1,
                    "round": 0.01,
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
        is_curve = True 
        
        try:
            points_data = json.loads(points_data_str)
            if isinstance(points_data, dict) and 'points' in points_data:
                is_curve = (points_data.get('mode', 'curve') == 'curve')
                points_data = points_data['points']
            elif not isinstance(points_data, list):
                raise ValueError("Graph data is not a list or valid dict.")
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
                print(f"[Element_SigmaGraph_Curve Warning] Invalid graph_data input format: {e}. Using default points.")
                return default_points_list
        except (ValueError, TypeError) as e:
            print(f"[Element_SigmaGraph_Curve Warning] Invalid graph_data input: {e}. Using default points.")
            return default_points_list

        try:
            valid_points = []
            for p in points_data:
                if isinstance(p, dict) and 'x' in p and 'y' in p and \
                   isinstance(p['x'], (int, float)) and not math.isnan(p['x']) and not math.isinf(p['x']) and \
                   isinstance(p['y'], (int, float)) and not math.isnan(p['y']) and not math.isinf(p['y']):
                    y_clamped = max(0.0, min(1.0, float(p['y'])))
                    valid_points.append({"x": float(p['x']), "y": y_clamped})
                else:
                    print(f"[Element_SigmaGraph_Curve Warning] Ignoring invalid point data: {p}")

            points = valid_points
            if len(points) != len(points_data):
                 print("[Element_SigmaGraph_Curve Warning] Some points in graph_data were invalid and ignored.")

        except Exception as e:
            print(f"[Element_SigmaGraph_Curve Warning] Error processing points: {e}. Using default.")
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
             return default_points_list, is_curve

        return unique_points, is_curve
    
    def _linear_interpolate(self, x_query, points):
        if not points:
            return 0.0
        if x_query <= points[0]['x']:
            return max(0.0, min(1.0, points[0]['y']))
        if x_query >= points[-1]['x']:
            return max(0.0, min(1.0, points[-1]['y']))
            
        for i in range(len(points) - 1):
            p0 = points[i]
            p1 = points[i+1]
            if p0['x'] <= x_query <= p1['x']:
                t = (x_query - p0['x']) / (p1['x'] - p0['x'])
                y = p0['y'] + t * (p1['y'] - p0['y'])
                return max(0.0, min(1.0, y))
        return max(0.0, min(1.0, points[-1]['y']))

    def _cubic_spline_coefficients(self, points):

        n = len(points) - 1  
        if n < 1:
            return []
        
        x = [p['x'] for p in points]
        y = [p['y'] for p in points]
        
        h = [x[i+1] - x[i] for i in range(n)]
        
        A = [[0.0] * (n+1) for _ in range(n+1)]
        b = [0.0] * (n+1)
        
        A[0][0] = 1.0
        A[n][n] = 1.0
        
        for i in range(1, n):
            A[i][i-1] = h[i-1]
            A[i][i] = 2.0 * (h[i-1] + h[i])
            A[i][i+1] = h[i]
            b[i] = 3.0 * ((y[i+1] - y[i]) / h[i] - (y[i] - y[i-1]) / h[i-1])
        
        M = self._solve_tridiagonal(A, b)
        
        coeffs = []
        for i in range(n):
            a = y[i]
            b_coef = (y[i+1] - y[i]) / h[i] - h[i] * (2*M[i] + M[i+1]) / 3.0
            c = M[i]
            d = (M[i+1] - M[i]) / (3.0 * h[i])
            coeffs.append({
                'a': a, 'b': b_coef, 'c': c, 'd': d,
                'x0': x[i], 'x1': x[i+1]
            })
        
        return coeffs

    def _solve_tridiagonal(self, A, b):
        """Thomas算法解三对角矩阵"""
        n = len(b)
        c_prime = [0.0] * n
        d_prime = [0.0] * n
        x = [0.0] * n
        
        c_prime[0] = A[0][1] / A[0][0] if n > 1 else 0
        d_prime[0] = b[0] / A[0][0]
        
        for i in range(1, n):
            denom = A[i][i] - A[i][i-1] * c_prime[i-1]
            if i < n-1:
                c_prime[i] = A[i][i+1] / denom
            d_prime[i] = (b[i] - A[i][i-1] * d_prime[i-1]) / denom
        
        x[n-1] = d_prime[n-1]
        for i in range(n-2, -1, -1):
            x[i] = d_prime[i] - c_prime[i] * x[i+1]
        
        return x

    def _evaluate_spline(self, x_query, coeffs, points):
        if not coeffs:
            return 0.0
        
        for coeff in coeffs:
            if coeff['x0'] <= x_query <= coeff['x1'] or \
               abs(x_query - coeff['x0']) < self.EPSILON or \
               abs(x_query - coeff['x1']) < self.EPSILON:
                dx = x_query - coeff['x0']
                y = coeff['a'] + coeff['b']*dx + coeff['c']*dx*dx + coeff['d']*dx*dx*dx
                return max(0.0, min(1.0, y))
        
        if x_query < coeffs[0]['x0']:
            return max(0.0, min(1.0, points[0]['y']))
        else:
            return max(0.0, min(1.0, points[-1]['y']))

    def _format_sigma_value(self, val):
        if abs(val) < 1e-10:
            val = 0.0
        val = max(0.0, min(1.0, val))
        return round(val, 10)

    def calculate_sigmas(self, steps, graph_data, max_value=1.0, custom_sigmas=None, latent=None, unique_id=None):
    
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
                points = [{"x": float(i) / new_steps, "y": self._format_sigma_value(float(v) / max_value)} for i, v in enumerate(sig_list)]
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
                    formatted_list = [self._format_sigma_value(v / max_value) * max_value for v in sig_list]
                    sigmas_tensor = torch.tensor(formatted_list, dtype=torch.float32, device="cpu")
                    
                return (sigmas_tensor, new_steps,)
            else:
                print("[Element_SigmaGraph_Curve Warning] custom_sigmas 输入的数据过短，已回退至界面曲线数据。")

        steps = max(1, int(steps))
        points, is_curve = self._validate_and_clean_points(graph_data)
        num_sigmas_to_generate = steps + 1

        coeffs = []
        if is_curve:
            coeffs = self._cubic_spline_coefficients(points)
        
        sigma_values = []
        for i in range(num_sigmas_to_generate):
            step_progress = i / steps
            step_progress = min(1.0, max(0.0, step_progress))
            
            if is_curve:
                sigma = self._evaluate_spline(step_progress, coeffs, points)
            else:
                sigma = self._linear_interpolate(step_progress, points)
            sigma_formatted = self._format_sigma_value(sigma) * max_value
            sigma_values.append(sigma_formatted)
            
        sigma_values.sort(reverse=True)
        
        for i in range(len(sigma_values) - 2, -1, -1):
            if sigma_values[i] <= sigma_values[i+1]:
                sigma_values[i] = sigma_values[i+1] + 1e-5
                
        current_max = sigma_values[0]
        if current_max > max_value:
            scale_factor = float(max_value) / current_max
            for i in range(len(sigma_values)):
                sigma_values[i] = sigma_values[i] * scale_factor
        # ==========================================
            
        sigmas_tensor = torch.tensor(sigma_values, dtype=torch.float32, device="cpu")
        return (sigmas_tensor, steps,)

NODE_CLASS_MAPPINGS = { "Element_SigmaGraph_Curve": Element_SigmaGraph_Curve }
NODE_DISPLAY_NAME_MAPPINGS = { "Element_SigmaGraph_Curve": "Sigma Schedule Graph (Curve)" }

# ==========================================
# 预设文件存储 API (与前端交互)
# ==========================================

base_dir = os.path.dirname(os.path.abspath(__file__))
presets_dir = os.path.join(base_dir, "presets")
presets_file = os.path.join(presets_dir, "Sigma_Curve_presets.json")

if not os.path.exists(presets_dir):
    os.makedirs(presets_dir, exist_ok=True)

@PromptServer.instance.routes.get("/element_easy/sigma_Curve_presets")
async def get_sigma_presets(request):
    if os.path.exists(presets_file):
        try:
            with open(presets_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return web.json_response(data)
        except Exception as e:
            print(f"[Element_SigmaGraph_Curve] 读取预设文件失败: {e}")
    return web.json_response([])  

@PromptServer.instance.routes.post("/element_easy/sigma_Curve_presets")
async def save_sigma_presets(request):
    try:
        data = await request.json()
        with open(presets_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        return web.json_response({"status": "success"})
    except Exception as e:
        print(f"[Element_SigmaGraph_Curve] 保存预设文件失败: {e}")
        return web.json_response({"status": "error", "message": str(e)}, status=500)
