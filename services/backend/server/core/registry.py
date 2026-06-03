import httpx
import re
from typing import Tuple, Any

def parse_image_name(full_image_name: str) -> Tuple[str, str, str]:
    """
    Parses an image string into Registry, Repository, and Tag.
    Example: 'ghcr.io/owner/repo:1.0' -> ('ghcr.io', 'owner/repo', '1.0')
    Example: 'ubuntu' -> ('registry-1.docker.io', 'library/ubuntu', 'latest')
    """
    if ":" in full_image_name and "/" not in full_image_name.split(":")[-1]:
        image_part, tag = full_image_name.rsplit(":", 1)
    else:
        image_part, tag = full_image_name, "latest"

    parts = image_part.split("/")
    
    if len(parts) == 1:
        registry = "registry-1.docker.io"
        repository = f"library/{parts[0]}"
    else:
        if "." in parts[0] or ":" in parts[0] or parts[0] == "localhost":
            registry = parts[0]
            repository = "/".join(parts[1:])
        else:
            registry = "registry-1.docker.io"
            repository = "/".join(parts)

    return registry, repository, tag


async def check_image_exists(
    full_image_name: str, 
    username: str | None = None, 
    password: str | None = None,
    schema: str = "https"
) -> bool:
    """
    Verifies if a Docker image exists on any OCI-compliant registry.
    Pass username/password for private registries.
    """
    registry, repository, tag = parse_image_name(full_image_name)
    
    manifest_url = f"{schema}://{registry}/v2/{repository}/manifests/{tag}"
    
    headers = {
        "Accept": "application/vnd.docker.distribution.manifest.v2+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.oci.image.index.v1+json"
    }
    
    auth = (username, password) if username and password else None
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.head(manifest_url, headers=headers, auth=auth or httpx.USE_CLIENT_DEFAULT)
        
        if response.status_code == 200:
            return True
        if response.status_code == 404:
            return False
            
        if response.status_code == 401:
            auth_header = response.headers.get("www-authenticate", "")
            
            if not auth_header.lower().startswith("bearer"):
                return False
            
            realm_match = re.search(r'realm="([^"]+)"', auth_header)
            service_match = re.search(r'service="([^"]+)"', auth_header)
            scope_match = re.search(r'scope="([^"]+)"', auth_header)
            
            if not realm_match:
                return False
                
            realm = realm_match.group(1)
            params = {}
            if service_match:
                params["service"] = service_match.group(1)
            
            if scope_match:
                params["scope"] = scope_match.group(1)
            else:
                params["scope"] = f"repository:{repository}:pull"
                
            token_resp = await client.get(realm, params=params, auth=auth)
            
            if token_resp.status_code != 200:
                return False
                
            token_data = token_resp.json()
            token = token_data.get("token") or token_data.get("access_token")
            
            if not token:
                return False
                
            headers["Authorization"] = f"Bearer {token}"
            retry_resp = await client.head(manifest_url, headers=headers)
            
            return retry_resp.status_code == 200
            
        return False

async def get_image_metadata(
    full_image_name: str,
    username: str | None = None,
    password: str | None = None,
    schema: str = "https"
) -> dict[str, Any]:
    """
    Fetches the digest and total size (sum of layers) of a Docker image.
    """
    registry, repository, tag = parse_image_name(full_image_name)
    manifest_url = f"{schema}://{registry}/v2/{repository}/manifests/{tag}"
    
    # We want the v2 manifest to get layer sizes
    headers = {
        "Accept": "application/vnd.docker.distribution.manifest.v2+json, application/vnd.oci.image.manifest.v1+json"
    }
    
    auth = (username, password) if username and password else None
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(manifest_url, headers=headers, auth=auth)
        
        # Note: If your registry requires auth, you should reuse the 
        # bearer token logic from your check_image_exists function here.

        if response.status_code != 200:
            raise Exception(f"Failed to fetch manifest: {response.status_code}")

        manifest = response.json()
        
        # The digest is usually in the headers
        digest = response.headers.get("Docker-Content-Digest") or response.headers.get("Etag")
        
        # Calculate total size from layers + config
        total_size = sum(layer.get("size", 0) for layer in manifest.get("layers", []))
        total_size += manifest.get("config", {}).get("size", 0)

        return {
            "digest": digest.strip('"') if digest else None,
            "size_bytes": total_size
        }