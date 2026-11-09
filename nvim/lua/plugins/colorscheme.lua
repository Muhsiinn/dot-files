return {
  {
    "rebelot/kanagawa.nvim",
    lazy = false,
    priority = 1000,

    opts = {
      transparent = true,
      theme = "dragon", -- wave, dragon, lotus
      dimInactive = false,

      colors = {
        theme = {
          all = {
            ui = {
              bg_gutter = "none",
              bg = "none",
              bg_p1 = "none",
              bg_p2 = "none",
            },
          },
        },
      },
    },

    config = function(_, opts)
      require("kanagawa").setup(opts)
      vim.cmd.colorscheme("kanagawa")

      local transparent = {
        "Normal",
        "NormalNC",
        "NormalFloat",
        "FloatBorder",
        "SignColumn",
        "EndOfBuffer",
        "WinSeparator",
        "FoldColumn",
        "StatusLine",
        "StatusLineNC",
      }

      for _, group in ipairs(transparent) do
        vim.api.nvim_set_hl(0, group, { bg = "none" })
      end
    end,
  },
}
