from __future__ import annotations
import io
import os
from posixpath import basename
import subprocess
from typing import Any
from zipfile import ZipFile, ZIP_DEFLATED

from PIL import Image
from tqdm import tqdm
from memory import Environment
import img2pdf


def get_unique_path(path: str):
    i = 0
    base, ext = os.path.splitext(path)
    while os.path.isfile(path):
        i += 1
        path = f"{base} ({i}){ext}"
    return path


class PdfConverter:

    def __init__(self, env: Environment):
        self.env = env

    def save_as_pdf(self, image_paths: tuple[str], savepath: str) -> None:
        savedir, savename = os.path.split(savepath)
        savename_noext = os.path.splitext(savename)[0]
        
        zip_dir = os.path.join(savedir, 'archives')
        pdf = self._fetch_images_as_pdf(image_paths)
        self._dump_in_pdf(pdf, savedir, savename_noext)
        self._pack_usedimages_into_zip(image_paths, zip_dir, savename_noext)
    
    def _fetch_images_as_pdf(self, image_paths: list[str]) -> Any:
        do_compress = self.env.enable_pdf_compression
        quality = self.env.compression_ratio
        images = list()
        for path in tqdm(image_paths, desc="Collecting images"):
            try:
                image = Image.open(path)
                if do_compress:
                    image = self._compress(image, quality)
                images.append(image)
            except FileNotFoundError:
                pass
        
        return img2pdf.convert(images)
    
    def _compress(self, image: Image, quality: int) -> Image:   
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=quality)
        return buffer.getvalue()
    
    def _dump_in_pdf(self, pdf: Any, output_dir: str, basename: str) -> None:
        output_path = os.path.join(output_dir, basename+'.pdf')
        with open(output_path, 'ab') as f:
            f.write(pdf)
    
    def _pack_usedimages_into_zip(self, image_paths: list[str], output_dir: str, basename: str) -> None:
        output_path = os.path.join(output_dir, basename+'.zip')
        os.makedirs(output_dir, exist_ok=True)

        self._create_zip(image_paths, output_path)
        self._remove_packed_images(image_paths)        

    def _create_zip(self, image_paths: list[str], output_path: str):
        if os.path.isfile(output_path):
            try:
                os.remove(output_path)
            except FileNotFoundError:
                pass
        
        with ZipFile(output_path, 'a') as zf:
            for path in tqdm(image_paths, desc="Exporting to zip"):
                try:
                    zf.write(path, basename(path), compress_type=ZIP_DEFLATED)
                except FileNotFoundError:
                    pass
        
    def _remove_packed_images(self, image_paths: list[str]) -> None:
        for path in tqdm(image_paths, "Removing images"):
            try:
                os.remove(path)
            except FileNotFoundError:
                pass


class PassLock:

    def __init__(self, env: Environment):
        self.env = env

    def try_encrypt(self, pdfpath: str, savepath: str, pw: str) -> bool:
        lv = self._enc_length()
        savepath = get_unique_path(savepath)
        
        try:
            subprocess.run(f'qpdf --encrypt {pw} {pw} {lv} --use-aes=y -- "{pdfpath}" "{savepath}"')
        except Exception as e:
            raise Exception('In encryption process, following error occurred:\n {e}')

    def try_decrypt(self, pdfpath: str, savepath: str, pw: str) -> bool:
        savepath = get_unique_path(savepath)
        try:
            subprocess.run(f'qpdf --password={pw} --decrypt "{pdfpath}" "{savepath}"')
        except Exception as e:
            raise Exception('In decryption process, following error occurred:\n {e}')

    def is_encrypted(self, pdfpath: str) -> bool:
        exitcode = subprocess.run('qpdf --is-encrypted "{pdfpath}"').returncode
        if exitcode == 0:
            return True
        return False

    def _enc_length(self) -> int:
        lv = self.env.password_security_level
        if lv == 1:
            return 40
        elif lv == 2:
            return 128
        elif lv == 3:
            return 256
        else:
            raise ValueError(f'Security level must be 1, 2 or 3, not {lv}.')
