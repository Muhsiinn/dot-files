vim.keymap.set("n", "<leader>rf", function()
  require("conform").format()
end, { desc = "Format file" })
