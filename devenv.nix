{ pkgs, ... }:
{
  # TypeScript port, running on Cloudflare Workers.
  # wrangler (and the workerd runtime it bundles) is a pnpm devDependency in package.json, so the
  # version is pinned per project. The workerd binary from npm needs nix-ld on NixOS.
  languages.typescript.enable = true;
  languages.javascript = {
    enable = true;
    package = pkgs.nodejs_24;
    pnpm.enable = true;
  };

  # The Python version stays the reference implementation during the port: run its tests and
  # compare outputs (tests/golden_alcomath.json) against the TypeScript one.
  languages.python = {
    enable = true;
    package = pkgs.python313;
    uv = {
      enable = true;
      sync.enable = true;
    };
  };

  packages = with pkgs; [
    sqlite # inspect local D1 databases under .wrangler/state
    jq
  ];

  env.WRANGLER_SEND_METRICS = "false";

  enterShell = ''
    export PATH="$DEVENV_ROOT/node_modules/.bin:$PATH"
    echo "node $(node --version), pnpm $(pnpm --version), $(python --version)"
    [ -d node_modules ] || echo "run 'pnpm install' to get wrangler"
  '';

  enterTest = ''
    uv run pytest -q
    pnpm exec wrangler --version
  '';
}
