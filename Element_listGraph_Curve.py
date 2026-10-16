# Element_listGraph_Curve.py —— 通用数值列表曲线节点。
#
# 以 Element_SigmaGraph_Curve 为蓝本（曲线编辑器交互、三次样条插值、
# 预设槽、C/L 模式切换等全部保留），去除 sigmas 特有的三条限制：
#   1. 不再强制输出递减（去掉 sort(reverse=True) 与递减修正循环）
#   2. 不再强制 x=1 处 y=0（末端值完全由曲线决定）
#   3. 输出不再是 SIGMAS 张量，而是 FLOAT / INT 列表（INT = round(FLOAT)）
# 保留的约束：y 值大小遵从 max_value —— UI 内部仍归一化到 [0,1]，
# 输出值 = 归一化值 × max_value，即 y ∈ [0, max_value]。
#
# 与 sigma 语义的关键区别：输出列表长度 = steps（而非 steps+1）。
# N 个采样点均匀覆盖曲线 x∈[0,1]：x_i = i/(N-1)，首尾正好落在
# 曲线两端点上；steps=1 时输出单值（曲线在 x=0 处的值）。

import os
import json
import math
import re
from server import PromptServer
from aiohttp import web


class Element_listGraph_Curve:
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
                    "default": 20, "min": 1, "max": 10000,
                }),
                "graph_data": ("STRING", {
                    "default": default_points,
                    "multiline": True,
                }),
                "max_value": ("FLOAT", {
                    "default": 1.0000,
                    "min": 0.0001,
                    "max": 10000.0,
                    "step": 0.0001,
                    "round": 0.0001,
                }),
            },
        }

    RETURN_TYPES = ("FLOAT", "STRING",)
    RETURN_NAMES = ("float_list", "string_list",)
    FUNCTION = "calculate_values"
    CATEGORY = "Element_easy"

    def _validate_and_clean_points(self, points_data_str):
        """ 解析、校验并清理曲线点数据。与 SigmaGraph 相同的容错链路：
        JSON → 数字串解析 → 默认值兜底。y 始终 clamp 到 [0,1]（归一化域）。 """
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
                    # 单数字：水平恒值曲线（不隐含任何递减/归零语义）
                    points_data = [{"x": 0.0, "y": nums[0]}, {"x": 1.0, "y": nums[0]}]
                else:
                    points_data = [{"x": float(i) / (len(nums) - 1), "y": float(y)} for i, y in enumerate(nums)]
            except Exception as e:
                print(f"[Element_listGraph_Curve Warning] Invalid graph_data input format: {e}. Using default points.")
                return default_points_list, is_curve
        except (ValueError, TypeError) as e:
            print(f"[Element_listGraph_Curve Warning] Invalid graph_data input: {e}. Using default points.")
            return default_points_list, is_curve

        try:
            valid_points = []
            for p in points_data:
                if isinstance(p, dict) and 'x' in p and 'y' in p and \
                   isinstance(p['x'], (int, float)) and not math.isnan(p['x']) and not math.isinf(p['x']) and \
                   isinstance(p['y'], (int, float)) and not math.isnan(p['y']) and not math.isinf(p['y']):
                    y_clamped = max(0.0, min(1.0, float(p['y'])))
                    valid_points.append({"x": float(p['x']), "y": y_clamped})
                else:
                    print(f"[Element_listGraph_Curve Warning] Ignoring invalid point data: {p}")

            points = valid_points
            if len(points) != len(points_data):
                 print("[Element_listGraph_Curve Warning] Some points in graph_data were invalid and ignored.")

        except Exception as e:
            print(f"[Element_listGraph_Curve Warning] Error processing points: {e}. Using default.")
            return default_points_list, is_curve

        if not points:
             return default_points_list, is_curve

        has_start = any(abs(p['x'] - 0.0) < self.EPSILON for p in points)
        has_end = any(abs(p['x'] - 1.0) < self.EPSILON for p in points)

        if not has_start:
            start_y = min(points, key=lambda p: abs(p['x'] - 0.0))['y'] if points else 1.0
            start_y = max(0.0, min(1.0, start_y))
            points.append({"x": 0.0, "y": start_y})
        if not has_end:
            # 末端兜底取最近点 y（不强制为 0）
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

    def _format_value(self, val):
        """归一化域 [0,1] 的浮点精度修复"""
        if abs(val) < 1e-10:
            val = 0.0
        if abs(val - 1.0) < 1e-10:
            val = 1.0
        val = max(0.0, min(1.0, val))
        return round(val, 10)

    def calculate_values(self, steps, graph_data, max_value=1.0):
        # steps 契约为 INT，但工作流存量/外部写值可能送来浮点。
        # int() 截断（int(6.6)=6）曾造成"输出比 steps 少 1"；
        # 四舍五入，与前端加载时的量化保持一致。
        steps = max(1, int(float(steps) + 0.5))
        points, is_curve = self._validate_and_clean_points(graph_data)

        coeffs = []
        if is_curve:
            coeffs = self._cubic_spline_coefficients(points)

        # 与 SigmaGraph 的核心区别：
        # 1) 输出长度 = steps（非 steps+1）
        # 2) N 个采样点均匀覆盖 x∈[0,1]：x_i = i/(N-1)，
        #    首尾正好落在曲线两端点；steps=1 时取曲线起点单值
        # 3) 不做任何递减 / 末端归零 / 重排序修正——每个采样点
        #    的值完全由曲线在该处的形状决定
        float_values = []
        for i in range(steps):
            if steps > 1:
                step_progress = i / (steps - 1)
            else:
                step_progress = 0.0
            step_progress = min(1.0, max(0.0, step_progress))

            if is_curve:
                v = self._evaluate_spline(step_progress, coeffs, points)
            else:
                v = self._linear_interpolate(step_progress, points)
            float_values.append(self._format_value(v) * max_value)

        string_list = ", ".join(f"{v:g}" for v in float_values)

        return (float_values, string_list,)


NODE_CLASS_MAPPINGS = { "Element_listGraph_Curve": Element_listGraph_Curve }
NODE_DISPLAY_NAME_MAPPINGS = { "Element_listGraph_Curve": "List Schedule Graph (Curve)" }

# ==========================================
# 预设文件存储 API (与前端交互；独立于 Sigma_Curve 预设，互不覆盖)
# ==========================================

base_dir = os.path.dirname(os.path.abspath(__file__))
presets_dir = os.path.join(base_dir, "presets")
presets_file = os.path.join(presets_dir, "List_Curve_presets.json")

if not os.path.exists(presets_dir):
    os.makedirs(presets_dir, exist_ok=True)

@PromptServer.instance.routes.get("/element_easy/list_Curve_presets")
async def get_list_presets(request):
    if os.path.exists(presets_file):
        try:
            with open(presets_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return web.json_response(data)
        except Exception as e:
            print(f"[Element_listGraph_Curve] 读取预设文件失败: {e}")
    return web.json_response([])

@PromptServer.instance.routes.post("/element_easy/list_Curve_presets")
async def save_list_presets(request):
    try:
        data = await request.json()
        with open(presets_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        return web.json_response({"status": "success"})
    except Exception as e:
        print(f"[Element_listGraph_Curve] 保存预设文件失败: {e}")
        return web.json_response({"status": "error", "message": str(e)}, status=500)
