import hashlib
import math
import io
from typing import Tuple, Optional, Dict, Any, List
from PIL import Image, ImageFilter, ExifTags
import numpy as np

from .config import IntegrityConfig

class ImageFingerprintService:
    """Production-grade image fingerprinting, perceptual hashing, quality analysis, and EXIF extraction."""

    # Supported Magic Byte Signatures
    MAGIC_SIGNATURES = {
        'jpeg': [b'\xFF\xD8\xFF'],
        'png': [b'\x89PNG\r\n\x1a\n'],
        'gif': [b'GIF87a', b'GIF89a'],
        'webp': [b'RIFF']  # Note: byte 8-12 must be 'WEBP'
    }

    @classmethod
    def validate_image_security(cls, file_stream, filename: str, max_size_bytes: int = 5 * 1024 * 1024) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Validate file structure against OWASP recommendations:
        - Check magic bytes (prevent MIME spoofing)
        - Check file size limit
        - Verify PIL structural decoding
        Returns: (is_valid, mime_type, error_message)
        """
        file_stream.seek(0, 2)
        size = file_stream.tell()
        file_stream.seek(0)

        if size > max_size_bytes:
            return False, None, f"File size ({round(size / (1024*1024), 2)}MB) exceeds maximum permitted limit (5MB)."

        if size < 16:
            return False, None, "File is too small or truncated."

        header = file_stream.read(16)
        file_stream.seek(0)

        detected_format = None
        # Check JPEG
        if header.startswith(b'\xFF\xD8\xFF'):
            detected_format = 'image/jpeg'
        # Check PNG
        elif header.startswith(b'\x89PNG\r\n\x1a\n'):
            detected_format = 'image/png'
        # Check GIF
        elif header.startswith(b'GIF87a') or header.startswith(b'GIF89a'):
            detected_format = 'image/gif'
        # Check WEBP
        elif header.startswith(b'RIFF') and len(header) >= 12 and header[8:12] == b'WEBP':
            detected_format = 'image/webp'
        else:
            return False, None, "File signature (magic bytes) does not match valid JPEG, PNG, GIF, or WEBP image."

        try:
            file_stream.seek(0)
            img = Image.open(file_stream)
            img.verify()
            file_stream.seek(0)
            return True, detected_format, None
        except Exception as e:
            file_stream.seek(0)
            return False, None, f"Image decoding validation failed: {str(e)}"

    @staticmethod
    def calculate_sha256(file_bytes: bytes) -> str:
        """Calculate cryptographic SHA-256 hash for exact duplicate detection."""
        return hashlib.sha256(file_bytes).hexdigest()

    @staticmethod
    def calculate_ahash(image: Image.Image) -> str:
        """
        Average Hash (aHash) - 64-bit.
        Resizes to 8x8, computes mean intensity, bits set if pixel >= mean.
        """
        resized = image.convert('L').resize((8, 8), Image.Resampling.LANCZOS)
        pixels = np.array(resized, dtype=np.float32).flatten().tolist()
        avg = sum(pixels) / len(pixels)
        bits = ''.join('1' if p >= avg else '0' for p in pixels)
        hex_str = f"{int(bits, 2):016x}"
        return hex_str

    @staticmethod
    def calculate_dhash(image: Image.Image) -> str:
        """
        Difference Hash (dHash) - 64-bit.
        Resizes to 9x8, compares adjacent horizontal pixels.
        Extremely resilient to gamma, contrast, and compression modifications.
        """
        resized = image.convert('L').resize((9, 8), Image.Resampling.LANCZOS)
        pixels = np.array(resized, dtype=np.float32).flatten().tolist()
        bits = []
        for row in range(8):
            for col in range(8):
                idx = row * 9 + col
                bits.append('1' if pixels[idx] > pixels[idx + 1] else '0')
        hex_str = f"{int(''.join(bits), 2):016x}"
        return hex_str

    @staticmethod
    def calculate_phash(image: Image.Image) -> str:
        """
        Perceptual Hash (pHash) using Discrete Cosine Transform (DCT) - 64-bit.
        Resizes to 32x32, performs 2D DCT, extracts 8x8 low frequency AC components.
        """
        resized = image.convert('L').resize((32, 32), Image.Resampling.LANCZOS)
        matrix = np.array(resized, dtype=np.float32)

        # 2D Discrete Cosine Transform
        # Use separable 1D DCT using standard orthogonal DCT-II formula
        def dct_1d(x):
            N = x.shape[0]
            n = np.arange(N)
            k = np.arange(N).reshape(-1, 1)
            weights = np.sqrt(2 / N) * np.cos(np.pi * (2 * n + 1) * k / (2 * N))
            weights[0] *= 1 / np.sqrt(2)
            return np.dot(weights, x)

        dct_matrix = dct_1d(dct_1d(matrix).T).T

        # Extract top-left 8x8 low-frequency components (excluding DC component [0, 0])
        low_freq = dct_matrix[:8, :8].flatten()
        ac_components = low_freq[1:]  # skip DC
        median_val = float(np.median(ac_components))

        bits = ''.join('1' if val > median_val else '0' for val in low_freq)
        hex_str = f"{int(bits, 2):016x}"
        return hex_str

    @staticmethod
    def hamming_distance(hex1: str, hex2: str) -> int:
        """Compute bitwise Hamming distance between two hex hash strings."""
        if not hex1 or not hex2:
            return 64
        val1 = int(hex1, 16)
        val2 = int(hex2, 16)
        return bin(val1 ^ val2).count('1')

    @classmethod
    def generate_visual_embedding(cls, image: Image.Image) -> List[float]:
        """
        Generate a 64-dimensional normalized color and spatial feature vector.
        Combines 4x4 spatial grid color statistics with texture energy.
        """
        rgb_img = image.convert('RGB').resize((64, 64), Image.Resampling.BILINEAR)
        arr = np.array(rgb_img, dtype=np.float32) / 255.0

        features = []
        # 4x4 spatial grid = 16 blocks, 3 color channels mean + 1 std = 64 features
        block_h, block_w = 16, 16
        for r in range(4):
            for c in range(4):
                r_start, r_end = r * block_h, (r + 1) * block_h
                c_start, c_end = c * block_w, (c + 1) * block_w
                block = arr[r_start:r_end, c_start:c_end]
                r_mean = float(np.mean(block[:, :, 0]))
                g_mean = float(np.mean(block[:, :, 1]))
                b_mean = float(np.mean(block[:, :, 2]))
                intensity_std = float(np.std(block))
                features.extend([r_mean, g_mean, b_mean, intensity_std])

        # Normalize vector
        vec = np.array(features, dtype=np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return [round(float(x), 4) for x in vec]

    @staticmethod
    def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """Compute cosine similarity between two feature vectors."""
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0
        v1 = np.array(vec1, dtype=np.float32)
        v2 = np.array(vec2, dtype=np.float32)
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return float(np.clip(np.dot(v1, v2) / (norm1 * norm2), 0.0, 1.0))

    @classmethod
    def evaluate_quality(cls, image: Image.Image) -> Dict[str, Any]:
        """
        Detect low-quality images:
        - Completely blank images
        - Extremely dark images
        - Extremely blurry images
        - Extremely low resolution
        Returns: { 'is_usable': bool, 'warning': Optional[str], 'metrics': dict }
        """
        width, height = image.size
        warnings = []

        # Resolution check
        if width < 150 or height < 150:
            warnings.append(f"Low resolution image ({width}x{height}px). Clear evidence recommended.")

        gray = image.convert('L')
        arr = np.array(gray, dtype=np.float32)
        std_dev = float(np.std(arr))
        mean_val = float(np.mean(arr))

        # Blank / uniform color check
        if std_dev < 3.5:
            warnings.append("Image is completely blank or uniform without clear visual content.")

        # Extreme darkness check
        if mean_val < 15.0:
            warnings.append("Image is extremely dark / underexposed.")

        # Extreme blur detection using simple 3x3 Laplacian kernel variance
        # Kernel: [[0, 1, 0], [1, -4, 1], [0, 1, 0]]
        laplacian_kernel = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float32)
        # Fast downscale for blur detection
        small = gray.resize((128, 128), Image.Resampling.BILINEAR)
        s_arr = np.array(small, dtype=np.float32)
        # Convolution
        padded = np.pad(s_arr, 1, mode='edge')
        laplacian = (
            padded[0:128, 1:129]
            + padded[2:130, 1:129]
            + padded[1:129, 0:128]
            + padded[1:129, 2:130]
            - 4 * s_arr
        )
        blur_score = float(np.var(laplacian))
        if blur_score < 30.0 and std_dev >= 3.5:
            warnings.append(f"Image appears noticeably blurry (sharpness score: {round(blur_score, 1)}).")

        warning_text = "; ".join(warnings) if warnings else None
        return {
            "is_usable": len(warnings) == 0 or (std_dev >= 3.5 and mean_val >= 15.0),
            "warning": warning_text,
            "metrics": {
                "width": width,
                "height": height,
                "mean_brightness": round(mean_val, 1),
                "contrast_std": round(std_dev, 1),
                "sharpness_score": round(blur_score, 1)
            }
        }

    @classmethod
    def extract_metadata(cls, image: Image.Image) -> Dict[str, Any]:
        """
        Extract EXIF metadata: Camera model, timestamp, GPS coordinates, editing software.
        Treats EXIF as supporting signal only; never flags solely because EXIF is absent.
        """
        metadata: Dict[str, Any] = {
            "camera_model": None,
            "software": None,
            "timestamp": None,
            "latitude": None,
            "longitude": None,
            "is_manipulated": False,
            "manipulation_signals": []
        }

        try:
            exif = image._getexif()
            if not exif:
                return metadata

            tag_map = {ExifTags.TAGS[k]: v for k, v in exif.items() if k in ExifTags.TAGS}

            # Camera
            make = str(tag_map.get('Make', '')).strip()
            model = str(tag_map.get('Model', '')).strip()
            if make or model:
                metadata['camera_model'] = f"{make} {model}".strip()

            # Software
            software = str(tag_map.get('Software', '')).strip()
            if software:
                metadata['software'] = software
                suspicious_software = ['photoshop', 'gimp', 'canva', 'facetune', 'snapseed', 'picsart']
                if any(s in software.lower() for s in suspicious_software):
                    metadata['is_manipulated'] = True
                    metadata['manipulation_signals'].append(f"Image edited with software: {software}")

            # Timestamp
            metadata['timestamp'] = tag_map.get('DateTimeOriginal') or tag_map.get('DateTime')

            # GPS
            gps_info = tag_map.get('GPSInfo')
            if gps_info:
                lat, lng = cls._parse_gps(gps_info)
                metadata['latitude'] = lat
                metadata['longitude'] = lng

        except Exception:
            pass

        return metadata

    @staticmethod
    def _parse_gps(gps_info: dict) -> Tuple[Optional[float], Optional[float]]:
        """Convert EXIF GPS coordinates (degrees, minutes, seconds) to decimal degrees."""
        def to_decimal(dms, ref):
            try:
                degrees = float(dms[0])
                minutes = float(dms[1])
                seconds = float(dms[2])
                dec = degrees + (minutes / 60.0) + (seconds / 3600.0)
                if ref in ['S', 'W']:
                    dec = -dec
                return dec
            except Exception:
                return None

        # Exif GPS tags: 1=LatRef, 2=Lat, 3=LngRef, 4=Lng
        lat_ref = gps_info.get(1)
        lat_dms = gps_info.get(2)
        lng_ref = gps_info.get(3)
        lng_dms = gps_info.get(4)

        lat = to_decimal(lat_dms, lat_ref) if lat_dms and lat_ref else None
        lng = to_decimal(lng_dms, lng_ref) if lng_dms and lng_ref else None
        return lat, lng

    @staticmethod
    def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate the great circle distance in meters between two GPS coordinates."""
        if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
            return float('inf')

        R = 6371000.0  # Earth radius in meters
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)

        a = (
            math.sin(delta_phi / 2.0) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
        )
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
        return R * c
