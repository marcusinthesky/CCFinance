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
      vale
      (texliveInfraOnly.withPackages (ps: [
        ps.chktex
        ps.kpathsea
        ps.texcount
        ps.latex-bin
        ps.graphics
        ps.epstopdf-pkg
        ps.underscore
        ps.lm
        # arXiv source submission compiled with pdfLaTeX.
        ps.geometry
        ps.hyperref
        # AAAI-27 submission template and bibliography.
        ps.bibtex
        ps.iftex
        ps.newtx
        ps.fontaxes
        ps.xkeyval
        ps.xstring
        ps.etoolbox
        ps.kastrup
        ps.psnfss
        ps.helvetic
        ps.courier
        ps.placeins
        ps.xcolor
        ps.url
        ps.natbib
        ps.caption
        ps.booktabs
        ps.amsmath
        ps.amsfonts
        ps.amscls
        ps.tools
        ps.cm-super
        ps.ec
        ps.xpatch
        ps.carlisle
        ps.oberdiek
        ps.kvoptions
        ps.l3packages
        ps.dvips
      ]))
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
