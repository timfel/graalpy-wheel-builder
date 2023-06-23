from graalpy_wheel_builder import *

BuildSpec(name="psutil")
numpy = BuildSpec(
    name="numpy",
    extra_versions=["1.21.6", "1.22.4", "1.23.1", "1.23.4"],
    system_dependencies={
        Linux: ["gcc-toolset-12-gcc-gfortran", "openblas-devel"],
        Mac: ["gcc", "openblas"],
    },
)
BuildSpec(
    name="pandas",
    system_dependencies=["openblas"],
    spec_dependencies=[numpy],
)
pybind11 = BuildSpec(name="pybind11")
ninja = BuildSpec(name="ninja")
pillow = BuildSpec(
    name="Pillow",
    system_dependencies={
        Linux: ["libtiff-devel", "libjpeg-devel", "openjpeg2-devel", "zlib-devel",
                "freetype-devel", "lcms2-devel", "libwebp-devel"],
        Mac: ["libjpeg", "libtiff", "little-cms2", "openjpeg", "webp"],
    },
)
contourpy = BuildSpec(
    name="contourpy",
    spec_dependencies=[ninja, pybind11, numpy],
)
kiwisolver = BuildSpec(
    name="kiwisolver",
    spec_dependencies=[pybind11],
)
BuildSpec(
    name="matplotlib",
    spec_dependencies=[pillow, kiwisolver, numpy, contourpy],
    system_dependencies=["openblas"],
)
scipy = BuildSpec(
    name="scipy",
    spec_dependencies=[numpy],
    system_dependencies={
        Linux: ["gcc-toolset-9", "gcc-toolset-9-gcc-gfortran", "openblas-devel"],
        Mac: ["gcc", "openblas", "pkg-config"],
    },
    before_build={
        Linux: ["source /opt/rh/gcc-toolset-9/enable"],
        Mac: [
            "export PKG_CONFIG_PATH=/opt/homebrew/opt/openblas/lib/pkgconfig",
            "export FFLAGS=-fallow-argument-mismatch",
        ],
    },
)
BuildSpec(
    name="scikit-learn",
    spec_dependencies=[numpy, scipy],
    system_dependencies=["openblas"],
    before_build={
        Mac: [
            "export PKG_CONFIG_PATH=/opt/homebrew/opt/openblas/lib/pkgconfig",
            "export FFLAGS=-fallow-argument-mismatch",
        ],
    },
)
cffi = BuildSpec(
    name="cffi",
    system_dependencies={
        Linux: ["libffi-devel"],
        Mac: ["libffi"],
    },
)
pyyaml = BuildSpec(name="PyYAML")
cmake = BuildSpec(name="cmake")
BuildSpec(
    name="torch",
    spec_dependencies=[numpy, ninja, cmake, pybind11, cffi, pyyaml],
    system_dependencies={
        Linux: ["openblas-devel", "/usr/bin/cmake", "/usr/bin/sudo"],
        Mac: ["openblas", "cmake"],
    },
    before_build={
        Mac: [
            "export USE_CUDA=0",
            "export PKG_CONFIG_PATH=/opt/homebrew/opt/openblas/lib/pkgconfig",
        ],
    },
    custom_steps = [{
        "uses": "Jimver/cuda-toolkit@v0.2.11",
        "id": "cuda-toolkit",
        "if": "runner.os != 'macOS'",
        "with": {
            "cuda": "11.7.0",
        },
    }],
    environment={
        "MAX_JOBS": 4,
        "BUILD_TEST": 0,
    },
)


if __name__ == "__main__":
    import os
    import sys
    import yaml

    # We tweak pyyaml to produce yaml files formatted like in the Github examples
    # for consistency
    def literal_str_representer(dumper: yaml.Dumper, data):
        if "\n" in data:
            return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
        else:
            return dumper.represent_scalar('tag:yaml.org,2002:str', data)

    yaml.add_representer(str, literal_str_representer)

    class IndentedListDumper(yaml.Dumper):
        def increase_indent(self, flow=False, indentless=False):
            return super().increase_indent(flow, False)

    # We generate separate workflow files for each platform, because github
    # chokes on workflow files with too many jobs
    original_platforms = [spec.platforms for spec in BuildSpec.get_instances()]

    # We also add needs relationships between all jobs, to make a totally
    # ordered queue. This is because there's no good way to limit concurrency
    # on github or act, and we do not want to overload our worker
    linked_specs = []
    unlinked_specs = list(BuildSpec.get_instances())
    last_spec = None
    while unlinked_specs:
        for spec in sorted(unlinked_specs[:], key=lambda s: 0 if last_spec in s.spec_dependencies else 1):
            if all(dep in linked_specs for dep in spec.spec_dependencies):
                linked_specs.append(spec)
                unlinked_specs.remove(spec)
                if last_spec and last_spec not in spec.spec_dependencies:
                    spec.spec_dependencies.append(last_spec)
                last_spec = spec

    for p in PLATFORMS:
        for spec, original_platform in zip(linked_specs, original_platforms):
            if p in original_platform:
                spec.platforms = [p]
            else:
                spec.platforms = []
            jobs = create_jobs(linked_specs, f"build-{p.name}-{p.arch}-wheels", "workflow_dispatch")
        with open(os.path.join(os.path.dirname(__file__), ".github", "workflows", f"build-{p.name}-{p.arch}-wheels.yml"), "w") as f:
            f.write(yaml.dump(jobs, Dumper=IndentedListDumper, sort_keys=False))

    # act workflow for local execution. These need node explictly in the Linux docker containers
    for spec, original_platform in zip(linked_specs, original_platforms):
        spec.platforms = original_platform
        spec.get_downstream_specs().clear()
    jobs = create_jobs(linked_specs, "build-act-wheels", "workflow_dispatch")
    with open(os.path.join(os.path.dirname(__file__), ".github", "workflows", "build-act-wheels.yml"), "w") as f:
        f.write(yaml.dump(jobs, Dumper=IndentedListDumper, sort_keys=False))

    # generate a workflow to create the repository
    repo_job = {
        "name": "build-repository",
        "on": "workflow_dispatch",
        "jobs": {
            "build-repo": {
                "runs-on": "ubuntu-latest",
                "steps": [
                    {
                        "name": f"Download artifacts for {p.name}-{p.arch}",
                        "uses": "dawidd6/action-download-artifact@v2",
                        "with": {
                            "workflow": f"build-{p.name}-{p.arch}-wheels",
                        },
                    } for p in PLATFORMS
                ] + [
                    {
                        "name": "Set up Python",
                        "uses": "actions/setup-python@v4",
                        "with": {
                            "python-version": "3.10",
                        },
                    },
                    {
                        "name": "Create repository",
                        "run": "python ${GITHUB_WORKSPACE}/generate_repository.py",
                    },
                    {
                        "name": "Store repository",
                        "uses": "umutozd/upload-artifact@5c459179e7745e2c730c50b10a6459da0b6f25db",
                        "with": {
                            "name": "repository",
                            "path": "repository.zip",
                            "if-no-files-found": "error",
                        },
                    },
                ],
            },
        },
    }
    with open(os.path.join(os.path.dirname(__file__), ".github", "workflows", "build-repository.yml"), "w") as f:
        f.write(yaml.dump(repo_job, Dumper=IndentedListDumper, sort_keys=False))

    print("Generated specs to build the following packages\n\t", "\n\t".join([s.name for s in linked_specs]), sep="")
