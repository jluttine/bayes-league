{ pkgs ? import <nixpkgs> {} }:

with pkgs;

mkShell {
  buildInputs = [
    (python3.withPackages (ps: with ps; [
      django
      numpy
      scipy
      jax
      jaxlib
      ipython
    ]))
  ];
}
