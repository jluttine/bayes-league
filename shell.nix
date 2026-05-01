{ pkgs ? import <nixpkgs> {} }:

with pkgs;

mkShell {
  buildInputs = [
    (
      (
        python3.override {
          packageOverrides = self: super: {
            django = super.django_4;
          };
        }
      ).withPackages (
        ps: with ps; let
          django-ordered-model = buildPythonPackage rec {
            pname = "django-ordered-model";
            version = "3.7.4";
            format = "pyproject";
            src = fetchPypi {
              inherit pname version;
              hash = "sha256-8li5diUlwApTAJ6C+Li/KjqjFei0U+KB6P27/iuMs7o=";
            };
            nativeBuildInputs = [
              setuptools
            ];
            checkInputs = [
              djangorestframework
            ];
            propagatedBuildInputs = [
              django
            ];
            checkPhase = ''
              runHook preCheck
              ${python.interpreter} -m django test --settings tests.settings
              runHook postCheck
            '';
            pythonImportsCheck = [ "ordered_model" ];
          };
        in [
          build
          numpy
          scipy
          autograd
          ipython
          django
          django-ordered-model
          pytest
          beautifulsoup4
        ]
      )
    )
  ];
}
