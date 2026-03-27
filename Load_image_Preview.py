import os
import glob
import base64
import io
import torch
import numpy as np
from PIL import Image, ImageOps, ImageSequence
import folder_paths
from server import PromptServer
from aiohttp import web
import node_helpers

# --- API 路由定义 ---
@PromptServer.instance.routes.post("/element_easy/images")
async def get_images(request):
    body = await request.json()
    folder_path = body.get("folder_path", folder_paths.get_output_directory())
    sort_method = body.get("sort_method", "newest_first")
    
    if not os.path.exists(folder_path) or not os.path.isdir(folder_path):
        return web.json_response({})

    image_extensions = ["*.png", "*.jpg", "*.jpeg", "*.gif", "*.bmp", "*.webp", "*.tiff"]
    files = []
    for ext in image_extensions:
        files.extend(glob.glob(os.path.join(folder_path, ext)))
        files.extend(glob.glob(os.path.join(folder_path, ext.upper())))

    if sort_method == "name_asc":
        files.sort(key=lambda x: os.path.basename(x).lower())
    elif sort_method == "name_desc":
        files.sort(key=lambda x: os.path.basename(x).lower(), reverse=True)
    elif sort_method == "newest_first":
        files.sort(key=lambda x: os.path.getctime(x), reverse=True)
    elif sort_method == "oldest_first":
        files.sort(key=lambda x: os.path.getctime(x))
    elif sort_method == "recently_modified":
        files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    elif sort_method == "oldest_modified":
        files.sort(key=lambda x: os.path.getmtime(x))
    else:
        files.sort(key=lambda x: os.path.getctime(x), reverse=True)

    images = {}
    for file_path in files:
        item_name = os.path.basename(file_path)
        images[item_name] = item_name

    return web.json_response(images)

@PromptServer.instance.routes.get("/element_easy/view")
async def view_image(request):
    folder_path = request.query.get("folder_path", folder_paths.get_output_directory())
    filename = request.query.get("filename")
    
    if not filename or not os.path.exists(folder_path) or not os.path.isdir(folder_path):
        return web.Response(status=404)
        
    image_path = os.path.join(folder_path, filename)
    
    if not os.path.exists(image_path) or not os.path.commonpath([folder_path, os.path.abspath(image_path)]) == folder_path:
        return web.Response(status=404)

    return web.FileResponse(image_path, headers={"Content-Disposition": f"filename=\"{filename}\""})


# --- 节点定义 ---
class LoadImageWithPreview:
    @classmethod
    def INPUT_TYPES(s):
        output_dir = folder_paths.get_output_directory()
        return {
            "required": {
                "folder_path": ("STRING", {"default": output_dir, "multiline": False}),
                "selected_image": ("STRING", {"default": ""}),
                "sort_method": (["name_asc", "name_desc", "newest_first", "oldest_first", "recently_modified", "oldest_modified"], {"default": "newest_first"}),
            },
            "optional": {
                "mask_data": ("STRING", {"default": "", "multiline": True}), 
                "shape_data": ("STRING", {"default": "", "multiline": True}), 
            }
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "filename")
    FUNCTION = "load_image"
    CATEGORY = "Element_easy/image"
    DESCRIPTION = "浏览文件夹并加载图像，内置遮罩与图像编辑功能(支持画笔、橡皮、方形、圆形)。Browse folders and load images; built-in masking and image editing functions (supports brush, eraser, square, and circle)."

    def load_image(self, folder_path, selected_image, sort_method, mask_data="", shape_data=""):

        if not selected_image or not selected_image.strip():
            if not os.path.exists(folder_path) or not os.path.isdir(folder_path):
                raise ValueError(f"Directory does not exist: {folder_path}")
            
            image_extensions = [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff"]
            files = []
            for ext in image_extensions:
                files.extend(glob.glob(os.path.join(folder_path, ext)))
                files.extend(glob.glob(os.path.join(folder_path, ext.upper())))
            

            if sort_method == "name_asc":
                files.sort(key=lambda x: os.path.basename(x).lower())
            elif sort_method == "name_desc":
                files.sort(key=lambda x: os.path.basename(x).lower(), reverse=True)
            elif sort_method == "newest_first":
                files.sort(key=lambda x: os.path.getctime(x), reverse=True)
            elif sort_method == "oldest_first":
                files.sort(key=lambda x: os.path.getctime(x))
            elif sort_method == "recently_modified":
                files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
            elif sort_method == "oldest_modified":
                files.sort(key=lambda x: os.path.getmtime(x))
            else:
                files.sort(key=lambda x: os.path.getctime(x), reverse=True)
            
            if not files:
                raise ValueError(f"目录中没有图像文件: {folder_path}")
            
            selected_image = os.path.basename(files[0])
            print(f"[LoadImageWithPreview] Automatically select the first image: {selected_image}")
            
        image_path = os.path.join(folder_path, selected_image)
        if not os.path.exists(image_path):
            raise ValueError(f"Image not found: {image_path}")
            
        if not os.path.commonpath([folder_path, os.path.abspath(image_path)]) == folder_path:
            raise ValueError(f"Image path out of bounds: {image_path}")
        
        base_img = node_helpers.pillow(Image.open, image_path)
        
        shape_layer = None
        if shape_data and shape_data.startswith("data:image"):
            try:
                header, encoded = shape_data.split(",", 1)
                shape_bytes = base64.b64decode(encoded)
                shape_layer = Image.open(io.BytesIO(shape_bytes)).convert("RGBA")
            except Exception as e:
                print(f"Failed to resolve shape overlay: {e}")
        
        output_images = []
        for i in ImageSequence.Iterator(base_img):
            i = node_helpers.pillow(ImageOps.exif_transpose, i)
            i = i.convert("RGBA")
            
            if shape_layer is not None:
                if shape_layer.size != i.size:
                    current_shape_layer = shape_layer.resize(i.size, Image.LANCZOS)
                else:
                    current_shape_layer = shape_layer
                
                i = Image.alpha_composite(i, current_shape_layer)
            
            image_tensor = i.convert("RGB")
            image_tensor = np.array(image_tensor).astype(np.float32) / 255.0
            image_tensor = torch.from_numpy(image_tensor)[None,]
            output_images.append(image_tensor)
            
        if len(output_images) > 1:
            output_image = torch.cat(output_images, dim=0)
        else:
            output_image = output_images[0]

        if mask_data and mask_data.startswith("data:image"):
            try:
                header, encoded = mask_data.split(",", 1)
                mask_bytes = base64.b64decode(encoded)
                mask_img = Image.open(io.BytesIO(mask_bytes)).convert("L")
                
                if mask_img.size != base_img.size:
                    mask_img = mask_img.resize(base_img.size, Image.LANCZOS)
                
                mask_tensor = torch.from_numpy(np.array(mask_img).astype(np.float32) / 255.0)
            except Exception as e:
                print(f"Mask parsing failed: {e}")
                mask_tensor = torch.zeros((base_img.height, base_img.width), dtype=torch.float32)
        else:
            mask_tensor = torch.zeros((base_img.height, base_img.width), dtype=torch.float32)

        if len(mask_tensor.shape) == 2:
            mask_tensor = mask_tensor.unsqueeze(0)
            
        filename = os.path.basename(selected_image)
        
        return (output_image, mask_tensor, filename)