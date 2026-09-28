from pathlib import Path
from setuptools import find_packages, setup

package_name = "prevera_perception"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
        (f"share/{package_name}/launch", [
            str(p) for p in Path("launch").glob("*.launch.py")
        ]),
    ],
    install_requires=["setuptools", "numpy", "scikit-learn"],
    zip_safe=True,
    maintainer="Jeremy Gracey",
    maintainer_email="jeremy.a.gracey@gmail.com",
    description="PREVERA GUARDIAN+AI LIDAR fall detection perception stack.",
    license="Apache-2.0",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "fall_detector = prevera_perception.fall_detector_node:main",
            "synthetic_publisher = prevera_perception.synthetic_publisher_node:main",
        ],
    },
)
