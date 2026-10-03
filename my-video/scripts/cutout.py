# Cuts the person out of a light studio background: python3 scripts/cutout.py <photo.png>
import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage
import sys
src = sys.argv[1]
im = np.asarray(Image.open(src).convert("RGB")).astype(int)
mx, mn = im.max(2), im.min(2)
rows = np.arange(im.shape[0])[:, None]
# Stricter near the head (light hair), looser near the floor shadow.
thr = np.where(rows > 850, 175, 210)
bgish = (mn > thr) & (mx - mn < 20)
lab, _ = ndimage.label(bgish)
edge = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
bg = np.isin(lab, list(edge))
# Drop small speckles inside the background, keep the body solid.
fg = ~bg
fg = ndimage.binary_opening(fg, iterations=1)
alpha = Image.fromarray((fg * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2))
out = Image.open(src).convert("RGBA")
out.putalpha(alpha)
out.save("public/dancer.png")
