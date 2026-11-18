{ pkgs, lib, ... }:
{
  # KakkosVuohi runs as a Python Worker on Cloudflare (README, "Cloudflare Workers"), or as a
  # long running bot (Docker). wrangler and the workerd runtime it bundles are pnpm devDependencies
  # (package.json); pywrangler, which packages the Python Worker, is a uv dev dependency.
  # The workerd binary from npm needs nix-ld on NixOS.
  languages.javascript = {
    enable = true;
    package = pkgs.nodejs_24;
    pnpm.enable = true;
  };

  # 3.14: the Python of the Workers runtime at our compatibility date
  languages.python = {
    enable = true;
    package = pkgs.python314;
    uv = {
      enable = true;
      sync.enable = true;
    };
  };
  # pywrangler needs uv's Pyodide interpreter, which only exists as a download. The system Python
  # is still preferred for everything else.
  env.UV_PYTHON_DOWNLOADS = lib.mkForce "automatic";
  env.UV_PYTHON_PREFERENCE = lib.mkForce "system";

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
    uv run ruff check src tests
    pnpm exec wrangler --version
  '';
}
