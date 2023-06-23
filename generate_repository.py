"""
Set up a repository folder following
https://packaging.python.org/en/latest/guides/hosting-your-own-index/
"""

import glob
import gzip
import os
import re
import shutil
import sys

def normalize(name):
    """
    Taken from
    https://packaging.python.org/en/latest/specifications/name-normalization/#name-normalization
    """
    return re.sub(r"[-_.]+", "-", name).lower()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        workspace = sys.argv[1]
    else:
        workspace = os.environ["GITHUB_WORKSPACE"]
    # find wheels either locally in the workspace or in an act artifact root structure
    wheels = glob.glob(os.path.join(workspace, "**/*.whl")) or glob.glob(os.path.join(workspace, "**/**/*.whl.gz__"))
    repo = os.path.join(workspace, "repository")
    os.makedirs(repo, exist_ok=True)
    for wheel in wheels:
        print("Processing", wheel)
        parts = os.path.basename(wheel).split("-")
        for idx, part in enumerate(parts):
            if part.startswith("graalpy3") or part.startswith("py3"):
                version_idx = idx - 1
                break
        wheel_name = normalize("-".join(parts[:version_idx]))
        target_dir = os.path.join(repo, wheel_name)
        os.makedirs(target_dir, exist_ok=True)
        if wheel.endswith(".gz__"):
            with gzip.open(wheel, 'rb') as f_in:
                with open(os.path.join(target_dir, os.path.basename(wheel).replace(".gz__", "")), 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
        else:
            shutil.copy(wheel, target_dir)

    shutil.make_archive(f"{workspace}/repository", 'zip', repo)
