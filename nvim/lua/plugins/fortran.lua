return {
  -- Fortran language server and live diagnostics
  {
    "neovim/nvim-lspconfig",
    opts = function(_, opts)
      opts.servers = opts.servers or {}

      opts.servers.fortls = {
        cmd = {
          vim.fn.expand("~/.local/share/fortls/venv/bin/fortls"),
          "--notify_init",
          "--hover_signature",
          "--hover_language=fortran",
          "--use_signature_help",
        },
      }

      vim.diagnostic.config({
        virtual_text = {
          prefix = "●",
          spacing = 2,
        },
        signs = true,
        underline = true,
        severity_sort = true,
        update_in_insert = true,
        float = {
          border = "rounded",
          source = "if_many",
        },
      })
    end,
  },

  -- Fortran syntax highlighting
  {
    "nvim-treesitter/nvim-treesitter",
    opts = function(_, opts)
      opts.ensure_installed = opts.ensure_installed or {}
      vim.list_extend(opts.ensure_installed, { "fortran" })
    end,
  },

  -- GFortran compiler diagnostics via nvim-lint
  {
    "mfussenegger/nvim-lint",
    opts = function(_, opts)
      local lint = require("lint")

      opts.linters_by_ft = opts.linters_by_ft or {}
      opts.linters_by_ft.fortran = { "gfortran" }

      opts.linters = opts.linters or {}

      local severity_map = {
        Error = vim.diagnostic.severity.ERROR,
        ["Fatal Error"] = vim.diagnostic.severity.ERROR,
        Warning = vim.diagnostic.severity.WARN,
        Note = vim.diagnostic.severity.INFO,
        error = vim.diagnostic.severity.ERROR,
        warning = vim.diagnostic.severity.WARN,
        note = vim.diagnostic.severity.INFO,
      }

      opts.linters.gfortran = {
        cmd = "gfortran",

        args = {
          "-fsyntax-only",
          "-fdiagnostics-plain-output",
          "-Wall",
          "-Wextra",
          "-Wunused-variable",
          "-Wunused-dummy-argument",
        },

        stdin = false,
        append_fname = true,
        stream = "both",
        ignore_exitcode = true,

        parser = require("lint.parser").from_pattern(
          "^([^:]+):(%d+):(%d+):%s+([^:]+):%s+(.*)$",
          { "file", "lnum", "col", "severity", "message" },
          severity_map,
          { source = "gfortran" }
        ),
      }
    end,
  },
}
