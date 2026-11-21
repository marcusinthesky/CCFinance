{ pkgs, lib, ... }:
{
  name = "ccfinance";
  packages =
    assert builtins.elem pkgs.stdenv.hostPlatform.system [
      "x86_64-linux"
      "aarch64-linux"
    ];
    with pkgs;
    [
      git
      just
      prek
      rumdl
      lychee
      nixfmt
      statix
      deadnix
      actionlint
      shellcheck
      shfmt
      tombi
      just-lsp
      ripgrep
      libarchive
      python313
      uv
      ruff
      pyrefly
      (callPackage ./pkgs/schematter.nix { })
      (callPackage ./pkgs/agentsync.nix { })
      patchelf
      tectonic
      tex-fmt
      (texliveInfraOnly.withPackages (ps: [ ps.chktex ]))
    ];
  env = {
    AWS_REQUEST_CHECKSUM_CALCULATION = "when_required";
    AWS_RESPONSE_CHECKSUM_VALIDATION = "when_required";
    UV_PYTHON_DOWNLOADS = "never";
    UV_PYTHON = "${pkgs.python313}/bin/python3";
    PROJECT_RUNTIME_LINKER = pkgs.stdenv.cc.bintools.dynamicLinker;
    LD_LIBRARY_PATH = lib.makeLibraryPath [ pkgs.stdenv.cc.cc.lib ];
    PROJECT_RUNTIME_LIBRARIES = lib.makeLibraryPath [
      pkgs.stdenv.cc.cc.lib
      pkgs.glibc
      pkgs.zlib
    ];
  };
  enterShell = "unset PYTHONPATH PYTHONHOME VIRTUAL_ENV";
  enterTest = "just check";
}
