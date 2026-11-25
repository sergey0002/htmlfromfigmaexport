"""Pixel comparisons that keep unequal dimensions and generate visible overlays."""
from __future__ import annotations
import io
from pathlib import Path


def save_comparison(reference: bytes, candidate: bytes, folder: Path, prefix: str, tolerance: int):
    from PIL import Image, ImageChops, ImageDraw

    first = Image.open(io.BytesIO(reference)).convert('RGB')
    second = Image.open(io.BytesIO(candidate)).convert('RGB')
    a_size, b_size = first.size, second.size
    size = (max(a_size[0], b_size[0]), max(a_size[1], b_size[1]))
    if size[0] * size[1] > 12_000_000:
        raise ValueError('Снимок слишком велик для надёжного построения карты различий')
    layers, areas = [], []
    for image in (first, second):
        layer = Image.new('RGB', size, 'white'); layer.paste(image, (0, 0)); layers.append(layer)
        area = Image.new('L', size, 0)
        ImageDraw.Draw(area).rectangle((0, 0, image.width - 1, image.height - 1), fill=255)
        areas.append(area)
    missing = ImageChops.difference(*areas)
    missing_pixels = missing.histogram()[255]
    raw = ImageChops.difference(*layers)
    # Regions outside either original image are always differences, including white pixels.
    raw.paste((255, 0, 255), mask=missing)
    channels = raw.split()
    max_channel = ImageChops.lighter(ImageChops.lighter(channels[0], channels[1]), channels[2])
    all_hist = max_channel.histogram()
    exact_ratio = (size[0] * size[1] - all_hist[0]) / (size[0] * size[1])
    mask = max_channel.point(lambda x: 255 if x > tolerance else 0)
    # Missing areas are visually different even if tolerance=255.
    mask = ImageChops.lighter(mask, missing)
    ratio = mask.histogram()[255] / (size[0] * size[1])
    overlay = Image.blend(*layers, 0.5)
    overlay.paste((255, 0, 255), mask=missing)
    red = Image.blend(layers[1], Image.new('RGB', size, (255, 0, 0)), 0.70)
    heatmap = Image.composite(red, layers[1], mask)
    heatmap.paste((255, 0, 255), mask=missing)
    folder.mkdir(parents=True, exist_ok=True)
    names = {key: f'{prefix}-{key}.png' for key in ('reference', 'candidate', 'diff', 'overlay', 'heatmap')}
    (folder/names['reference']).write_bytes(reference)
    (folder/names['candidate']).write_bytes(candidate)
    raw.save(folder/names['diff']); overlay.save(folder/names['overlay']); heatmap.save(folder/names['heatmap'])
    return {'reference_size': list(a_size), 'candidate_size': list(b_size), 'canvas_size': list(size),
            'missing_pixels': missing_pixels, 'difference_ratio': ratio, 'any_difference_ratio': exact_ratio, **names}
