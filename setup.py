from setuptools import setup, find_namespace_packages


if __name__ == "__main__":
    setup(
        install_requires=[
            "numpy",
            "scipy",
            "autograd",
        ],
        # NOTE: One needs to use find_namespace_packages instead of
        # find_packages in order to include non-Python files (e.g., templates)
        # in the package
        packages=find_namespace_packages(),
        include_package_data=True,
        scripts=["manage.py"],
        name="bayesleague",
    )
