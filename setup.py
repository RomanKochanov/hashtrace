from setuptools import find_packages, setup

setup(
    name="libraflow",
    version="0.1",
    author="Roman Kochanov",
    author_email="",
    description="Simple and transparent engine for research workflow management",
    url="https://github.com/romankochanov/libraflow",
    python_requires=">=3.5",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    install_requires=[
        "jeanny3",
        "numpy",
        "tabulate",
    ],
)
