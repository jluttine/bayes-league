{ pkgs ? import <nixpkgs> {} }:

with pkgs;

mkShell {
  buildInputs = [
    (python3.withPackages (ps: with ps; [
      build
      django
      numpy
      scipy
      autograd
      ipython
      django-ordered-model
    ]))
  ];
}
