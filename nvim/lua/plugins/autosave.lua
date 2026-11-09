return {
  {
    "okuuva/auto-save.nvim",
    event = { "InsertLeave", "TextChanged" },
    opts = {
      enabled = true,
      debounce_delay = 1000,

      trigger_events = {
        immediate_save = { "InsertLeave" },
        defer_save = { "TextChanged" },
        cancel_deferred_save = {},
      },

      condition = function(buf)
        local fn = vim.fn
        local utils = require("auto-save.utils.data")

        if fn.getbufvar(buf, "&buftype") ~= "" then
          return false
        end

        return true
      end,

      write_all_buffers = false,
    },
  },
}
