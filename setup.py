from setuptools import setup, find_packages


if __name__ == "__main__":
    setup(
        install_requires=[
            "numpy",
            "scipy",
            "autograd",
        ],
        packages=find_packages(),
        scripts=["manage.py"],
        name="bayesleague",
    )
