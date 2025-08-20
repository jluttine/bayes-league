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
        ps: with ps; [
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
