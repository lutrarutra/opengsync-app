from pydantic import BaseModel

from codeflower_db import types

from ..core.config import settings

class BucketProviderConfig(BaseModel):
    provider: types.BucketProvider
    access_key: str
    secret_key: str
    public_url: str | None = None


BUCKET_CONFIGS: dict[types.BucketProvider, BucketProviderConfig] = {
    types.BucketProvider.HETZNER: BucketProviderConfig(
        provider=types.BucketProvider.HETZNER,
        access_key=settings.HETZNER_ACCESS_KEY,
        secret_key=settings.HETZNER_SECRET_KEY,
    ),
    types.BucketProvider.CLOUDFLARE: BucketProviderConfig(
        provider=types.BucketProvider.CLOUDFLARE,
        access_key=settings.CLOUDFLARE_R2_ACCESS_KEY,
        secret_key=settings.CLOUDFLARE_R2_SECRET_KEY,
    ),
}


class ComputeProviderConfig(BaseModel):
    endpoint_url: str
    provider: types.ComputeProvider
    access_key: str
    secret_key: str
    regions: list[str]

COMPUTE_CONFIGS: dict[types.ComputeProvider, ComputeProviderConfig] = {
    types.ComputeProvider.AWS: ComputeProviderConfig(
        endpoint_url="https://ec2.amazonaws.com",
        provider=types.ComputeProvider.AWS,
        access_key=settings.AWS_ACCESS_KEY,
        secret_key=settings.AWS_SECRET_KEY,
        regions=["us-east-1", "us-west-1", "eu-west-1", "eu-central-1", "ap-southeast-1"]
    ),
    types.ComputeProvider.HETZNER: ComputeProviderConfig(
        endpoint_url="https://api.hetzner.cloud",
        provider=types.ComputeProvider.HETZNER,
        access_key=settings.HETZNER_ACCESS_KEY,
        secret_key=settings.HETZNER_SECRET_KEY,
        regions=["eu-central-1"]
    ),
    types.ComputeProvider.GCP: ComputeProviderConfig(
        endpoint_url="https://compute.googleapis.com/compute/v1",
        provider=types.ComputeProvider.GCP,
        access_key=settings.GCS_ACCESS_KEY,
        secret_key=settings.GCS_SECRET_KEY,
        regions=["us", "eu", "asia"]
    )
}