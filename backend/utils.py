import boto3
import json
import io
from botocore.exceptions import NoCredentialsError, ClientError
from backend.config import R2_ENDPOINT_URL, R2_BUCKET_NAME, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY

# ── Singleton S3 client ──
_s3_client = None

def _get_s3():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client(
            's3',
            endpoint_url=R2_ENDPOINT_URL,
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        )
    return _s3_client


def r2_enabled() -> bool:
    """Check if R2 credentials are configured."""
    return bool(R2_ENDPOINT_URL and R2_BUCKET_NAME and R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY)


# ─── JSON helpers (primary storage) ───────────────────────────────

def r2_write_json(key: str, data: dict) -> bool:
    """Write a JSON dict to R2."""
    try:
        body = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
        _get_s3().put_object(Bucket=R2_BUCKET_NAME, Key=key, Body=body, ContentType="application/json")
        return True
    except Exception as e:
        print(f"[R2] write_json FAILED for {key}: {e}")
        return False


def r2_read_json(key: str) -> dict | None:
    """Read a JSON dict from R2. Returns None if not found."""
    try:
        resp = _get_s3().get_object(Bucket=R2_BUCKET_NAME, Key=key)
        return json.loads(resp["Body"].read().decode("utf-8"))
    except ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
            return None
        print(f"[R2] read_json FAILED for {key}: {e}")
        return None
    except Exception as e:
        print(f"[R2] read_json FAILED for {key}: {e}")
        return None


# ─── Binary file helpers ──────────────────────────────────────────

def r2_write_bytes(key: str, data: bytes, content_type: str = "application/octet-stream") -> bool:
    """Write raw bytes to R2."""
    try:
        _get_s3().put_object(Bucket=R2_BUCKET_NAME, Key=key, Body=data, ContentType=content_type)
        return True
    except Exception as e:
        print(f"[R2] write_bytes FAILED for {key}: {e}")
        return False


def r2_read_bytes(key: str) -> bytes | None:
    """Read raw bytes from R2. Returns None if not found."""
    try:
        resp = _get_s3().get_object(Bucket=R2_BUCKET_NAME, Key=key)
        return resp["Body"].read()
    except ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
            return None
        print(f"[R2] read_bytes FAILED for {key}: {e}")
        return None
    except Exception as e:
        print(f"[R2] read_bytes FAILED for {key}: {e}")
        return None


def r2_delete(key: str) -> bool:
    """Delete an object from R2."""
    try:
        _get_s3().delete_object(Bucket=R2_BUCKET_NAME, Key=key)
        return True
    except Exception as e:
        print(f"[R2] delete FAILED for {key}: {e}")
        return False


def r2_exists(key: str) -> bool:
    """Check if an object exists in R2."""
    try:
        _get_s3().head_object(Bucket=R2_BUCKET_NAME, Key=key)
        return True
    except ClientError:
        return False
    except Exception:
        return False


def r2_list_keys(prefix: str) -> list[str]:
    """List all keys under a prefix in R2."""
    try:
        resp = _get_s3().list_objects_v2(Bucket=R2_BUCKET_NAME, Prefix=prefix)
        return [obj["Key"] for obj in resp.get("Contents", [])]
    except Exception as e:
        print(f"[R2] list_keys FAILED for {prefix}: {e}")
        return []


# ─── Legacy upload function (kept for backward compat) ────────────

def upload_to_r2(file_path, object_name):
    """Uploads a local file to Cloudflare R2 bucket."""
    try:
        _get_s3().upload_file(file_path, R2_BUCKET_NAME, object_name)
        print(f"File {file_path} uploaded to R2 as {object_name}.")
        return True
    except FileNotFoundError:
        print(f"File {file_path} not found.")
        return False
    except NoCredentialsError:
        print("Credentials not available for R2.")
        return False
    except Exception as e:
        print(f"An error occurred: {e}")
        return False