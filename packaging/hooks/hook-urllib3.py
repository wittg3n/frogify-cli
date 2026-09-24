# urllib3's optional backports.zstd probe resolves to a setuptools vendor alias
# during Analysis, although backports.zstd is not installed. This pulls in all
# setuptools machinery. The locked runtime does not provide the zstd extra.
excludedimports = ["backports"]
