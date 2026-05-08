import os
import re
import shutil
import subprocess
import zipfile


def _natural_key(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def list_image_files(folder_path):
    exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}
    files = []
    for name in os.listdir(folder_path):
        p = os.path.join(folder_path, name)
        if not os.path.isfile(p):
            continue
        ext = os.path.splitext(name)[1].lower()
        if ext in exts:
            files.append(p)
    files.sort(key=lambda p: _natural_key(os.path.basename(p)))
    return files


def export_pdf_from_images(image_paths, output_pdf_path):
    try:
        from PIL import Image
    except Exception as e:
        raise RuntimeError("PDF export requires Pillow (PIL).") from e

    if not image_paths:
        raise ValueError("No images provided.")

    images = []
    for p in image_paths:
        img = Image.open(p)
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        elif img.mode != "RGB":
            try:
                img = img.convert("RGB")
            except Exception:
                pass
        images.append(img)

    first, rest = images[0], images[1:]
    os.makedirs(os.path.dirname(output_pdf_path) or ".", exist_ok=True)
    first.save(output_pdf_path, "PDF", resolution=100.0, save_all=True, append_images=rest)

    for img in images:
        try:
            img.close()
        except Exception:
            pass

    return output_pdf_path


def _media_type_for_path(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".jpg", ".jpeg"):
        return "image/jpeg"
    if ext == ".png":
        return "image/png"
    if ext == ".webp":
        return "image/webp"
    if ext == ".gif":
        return "image/gif"
    if ext == ".bmp":
        return "image/bmp"
    return "application/octet-stream"


def export_epub_from_images(image_paths, output_epub_path, *, title="Manga", language="en"):
    if not image_paths:
        raise ValueError("No images provided.")

    os.makedirs(os.path.dirname(output_epub_path) or ".", exist_ok=True)

    book_id = "snekbooru-book"
    oebps = "OEBPS"
    images_dir = f"{oebps}/images"
    text_dir = f"{oebps}/text"

    with zipfile.ZipFile(output_epub_path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr(
            "META-INF/container.xml",
            """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
""",
            compress_type=zipfile.ZIP_DEFLATED,
        )

        manifest_items = []
        spine_items = []
        toc_points = []

        for i, img_path in enumerate(image_paths, start=1):
            img_name = f"page_{i:04d}{os.path.splitext(img_path)[1].lower()}"
            img_href = f"images/{img_name}"
            img_item_id = f"img{i}"
            with open(img_path, "rb") as f:
                zf.writestr(f"{images_dir}/{img_name}", f.read(), compress_type=zipfile.ZIP_DEFLATED)

            html_name = f"page_{i:04d}.xhtml"
            html_href = f"text/{html_name}"
            html_item_id = f"html{i}"
            page_title = f"Page {i}"
            xhtml = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="{language}">
  <head>
    <title>{page_title}</title>
    <meta charset="utf-8"/>
    <style type="text/css">
      body {{ margin: 0; padding: 0; }}
      img {{ display: block; max-width: 100%; height: auto; margin: 0 auto; }}
    </style>
  </head>
  <body>
    <img src="../{img_href}" alt="{page_title}"/>
  </body>
</html>
"""
            zf.writestr(f"{text_dir}/{html_name}", xhtml, compress_type=zipfile.ZIP_DEFLATED)

            manifest_items.append((img_item_id, img_href, _media_type_for_path(img_path)))
            manifest_items.append((html_item_id, html_href, "application/xhtml+xml"))
            spine_items.append(html_item_id)
            toc_points.append((i, html_href, page_title))

        nav_map = "\n".join(
            f"""  <navPoint id="navPoint-{i}" playOrder="{i}">
    <navLabel><text>{label}</text></navLabel>
    <content src="{href}"/>
  </navPoint>"""
            for i, href, label in toc_points
        )

        toc_ncx = f"""<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="{book_id}"/>
    <meta name="dtb:depth" content="1"/>
    <meta name="dtb:totalPageCount" content="0"/>
    <meta name="dtb:maxPageNumber" content="0"/>
  </head>
  <docTitle><text>{title}</text></docTitle>
  <navMap>
{nav_map}
  </navMap>
</ncx>
"""
        zf.writestr(f"{oebps}/toc.ncx", toc_ncx, compress_type=zipfile.ZIP_DEFLATED)

        manifest_xml = "\n".join(
            f'    <item id="{item_id}" href="{href}" media-type="{mt}"/>'
            for item_id, href, mt in manifest_items
        )
        manifest_xml += '\n    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'

        spine_xml = "\n".join(f'    <itemref idref="{item_id}"/>' for item_id in spine_items)

        content_opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="BookId" version="2.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>{title}</dc:title>
    <dc:language>{language}</dc:language>
    <dc:identifier id="BookId">{book_id}</dc:identifier>
  </metadata>
  <manifest>
{manifest_xml}
  </manifest>
  <spine toc="ncx">
{spine_xml}
  </spine>
</package>
"""
        zf.writestr(f"{oebps}/content.opf", content_opf, compress_type=zipfile.ZIP_DEFLATED)

    return output_epub_path


def export_png_zip_from_images(image_paths, output_zip_path):
    if not image_paths:
        raise ValueError("No images provided.")
    os.makedirs(os.path.dirname(output_zip_path) or ".", exist_ok=True)
    with zipfile.ZipFile(output_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for i, p in enumerate(image_paths, start=1):
            ext = os.path.splitext(p)[1].lower() or ".png"
            name = f"page_{i:04d}{ext}"
            zf.write(p, arcname=name)
    return output_zip_path


def export_kindle_epub_from_images(image_paths, output_epub_path, *, title="Manga", language="en"):
    return export_epub_from_images(image_paths, output_epub_path, title=title, language=language)


def _find_ebook_convert():
    return shutil.which("ebook-convert")


def export_mobi_from_images(image_paths, output_mobi_path, *, title="Manga", language="en"):
    exe = _find_ebook_convert()
    if not exe:
        raise RuntimeError("MOBI export requires Calibre (ebook-convert) installed and available on PATH.")
    tmp_epub = os.path.splitext(output_mobi_path)[0] + ".epub"
    export_epub_from_images(image_paths, tmp_epub, title=title, language=language)
    os.makedirs(os.path.dirname(output_mobi_path) or ".", exist_ok=True)
    proc = subprocess.run([exe, tmp_epub, output_mobi_path], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "ebook-convert failed").strip())
    return output_mobi_path


def cleanup_images_folder(folder, allowed_root):
    if not folder or not os.path.isdir(folder):
        return False
    if not allowed_root:
        return False
    try:
        root = os.path.abspath(allowed_root)
        target = os.path.abspath(folder)
        if os.path.commonpath([root, target]) != root:
            return False
    except Exception:
        return False

    removed_any = False
    for path in list_image_files(folder):
        try:
            os.remove(path)
            removed_any = True
        except Exception:
            pass

    try:
        if not os.listdir(folder):
            os.rmdir(folder)
    except Exception:
        pass

    return removed_any
