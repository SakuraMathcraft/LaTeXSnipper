from PIL import Image
from pix2tex.cli import LatexOCR

class ModelWrapper:
    def __init__(self):
        try:
            self.model = LatexOCR()
        except Exception as e:
            raise RuntimeError(f"加载 pix2tex 模型失败: {e}")

    def predict(self, pil_img: Image.Image) -> str:
        try:
            return self.model(pil_img).strip()
        except Exception as e:
            print("识别失败:", e)
            return ""
