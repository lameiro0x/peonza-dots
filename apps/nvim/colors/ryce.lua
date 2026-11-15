-- Colourscheme "ryce": whichever desktop theme is current. Each theme's colours
-- are generated at <state>/current/nvim/colors.lua (theme/templates/nvim); this
-- file only runs that one. No theme state yet (desktop not deployed, or a broken
-- file): habamax, still under the name "ryce" so the next switch repairs it.
--
-- It also follows switches. bin/ryce-theme replaces `current` by an atomic
-- rename, which a watch on the file itself would never see (it stays on the old
-- inode), so the watch is on the state directory and fires on the new `current`.
local state = vim.env.RYCE_THEME_STATE or vim.fs.joinpath(vim.env.HOME, ".local/state/ryce/theme")
local file = vim.fs.joinpath(state, "current", "nvim", "colors.lua")

local ok, err = pcall(dofile, file)
if not ok then
  vim.cmd.colorscheme("habamax")
  vim.g.colors_name = "ryce"
  vim.notify(("ryce: cannot load %s (%s); using habamax until a theme is set"):format(file, err), vim.log.levels.WARN)
end

if not vim.g.ryce_theme_watch then
  local watch = vim.uv.new_fs_event()
  local started = watch
    and watch:start(state, {}, vim.schedule_wrap(function(werr, name)
      if not werr and name == "current" and vim.g.colors_name == "ryce" then
        vim.cmd.colorscheme("ryce")
      end
    end))
  if started then
    vim.g.ryce_theme_watch = true
  elseif watch then
    watch:close()
  end
end
