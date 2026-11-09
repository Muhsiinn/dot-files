-- Hyprland 0.55+ Lua configuration

local mainMod = "SUPER"
local terminal = "wezterm"
local browser = "firefox"
local launcher = "rofi -show launch"

-- Keep both displays at native preferred mode; reduce only laptop UI scaling.
hl.monitor({ output = "eDP-1", mode = "preferred", position = "auto", scale = 1 })
hl.monitor({ output = "HDMI-A-1", mode = "preferred", position = "auto", scale = 1.0 })

-- Environment
hl.env("XCURSOR_SIZE", "24")
hl.env("HYPRCURSOR_SIZE", "24")
hl.env("QT_QPA_PLATFORM", "wayland;xcb")

-- Appearance
hl.config({
	general = {
		gaps_in = 1,
		gaps_out = 5,
		border_size = 2,
		layout = "dwindle",
		col = {
			active_border = {
				colors = { "rgba(e66f86ff)", "rgba(78283dff)" },
				angle = 45,
			},
			inactive_border = "rgba(6b4b55aa)",
		},
	},

	decoration = {
		rounding = 5,
		active_opacity = 1.0,
		inactive_opacity = 1.0,
		shadow = {
			enabled = true,
			range = 4,
			render_power = 3,
			color = 0xee000000,
		},
		blur = {
			enabled = true,
			size = 4,
			passes = 1,
			new_optimizations = true,
			xray = true,
		},
	},

	input = {
		kb_layout = "us",
		follow_mouse = 1,
		touchpad = {
			natural_scroll = false,
		},
	},

	dwindle = {
		preserve_split = true,
	},

	animations = {
		enabled = true,
	},
})

-- Startup applications
hl.on("hyprland.start", function()
	hl.exec_cmd("/home/anya/.config/hypr/startup-wallpaper.sh")
	hl.exec_cmd("waybar -c ~/.config/waybar/config.jsonc -s ~/.config/waybar/style.css")
	hl.exec_cmd("sh -c 'command -v qs >/dev/null 2>&1 && qs -c anya-headquarters --no-duplicate'")
	hl.exec_cmd("sh -c 'command -v qs >/dev/null 2>&1 && qs -c anya-notifications --no-duplicate'")
	hl.exec_cmd("python3 /home/anya/.config/waybar/scripts/anya-infiltrations.py")
	hl.exec_cmd("/usr/lib/polkit-gnome/polkit-gnome-authentication-agent-1")

	-- With getty autologin, Hyprland starts without a password prompt.
	-- The Anya lock screen keeps the desktop behind a password.
	hl.exec_cmd("sh -c '[ -f /etc/systemd/system/getty@tty1.service.d/autologin.conf ] && command -v hyprlock >/dev/null 2>&1 && hyprlock'")
end)

-- Use compositor blur only for the dedicated translucent quick-settings layer.
hl.layer_rule({
	match = { namespace = "crimson-quicksettings" },
	blur = true,
	ignore_alpha = 0.22,
})

hl.layer_rule({
	match = { namespace = "waybar" },
	blur = true,
	ignore_alpha = 0.65,
})

-- Slight glow behind the Anya notification popups.
hl.layer_rule({
	match = { namespace = "anya-notifications" },
	blur = true,
	ignore_alpha = 0.22,
})

-- Fullscreen video and presentations stay crisp.
hl.window_rule({
	match = { class = "^(firefox)$", fullscreen = true },
	no_blur = true,
})

-- Applications
hl.bind(mainMod .. " + RETURN", hl.dsp.exec_cmd(terminal))
hl.bind(mainMod .. " + SPACE", hl.dsp.exec_cmd(launcher))
hl.bind(mainMod .. " + B", hl.dsp.exec_cmd(browser))
hl.bind(mainMod .. " + E", hl.dsp.exec_cmd("wezterm start -- yazi"))

-- Window controls
hl.bind(mainMod .. " + Q", hl.dsp.window.close())
hl.bind(mainMod .. " + T", hl.dsp.window.float({ action = "toggle" }))
hl.bind(mainMod .. " + F", hl.dsp.window.fullscreen())
hl.bind(mainMod .. " + M", hl.dsp.exit())

-- Focus: Vim-style H/J/K/L
hl.bind(mainMod .. " + H", hl.dsp.focus({ direction = "left" }))
hl.bind(mainMod .. " + J", hl.dsp.focus({ direction = "down" }))
hl.bind(mainMod .. " + K", hl.dsp.focus({ direction = "up" }))
hl.bind(mainMod .. " + L", hl.dsp.focus({ direction = "right" }))
hl.bind("SUPER + SHIFT + H", hl.dsp.window.move({ direction = "l" }))
hl.bind("SUPER + SHIFT + J", hl.dsp.window.move({ direction = "d" }))
hl.bind("SUPER + SHIFT + K", hl.dsp.window.move({ direction = "u" }))
hl.bind("SUPER + SHIFT + L", hl.dsp.window.move({ direction = "r" }))

-- Workspaces 1–10 and move windows with Super+Shift
for i = 1, 10 do
	local key = i == 10 and "0" or tostring(i)
	-- Switch workspace on the current monitor
	hl.bind(
		mainMod .. " + " .. key,
		hl.dsp.focus({
			workspace = tostring(i),
			on_current_monitor = true,
		})
	)

	-- Move the active window to another workspace
	hl.bind(
		mainMod .. " + SHIFT + " .. key,
		hl.dsp.window.move({
			workspace = tostring(i),
		})
	)
end
-- Audio controls
hl.bind("XF86AudioRaiseVolume", hl.dsp.exec_cmd("wpctl set-volume -l 1 @DEFAULT_AUDIO_SINK@ 5%+"))
hl.bind("XF86AudioLowerVolume", hl.dsp.exec_cmd("wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-"))
hl.bind("XF86AudioMute", hl.dsp.exec_cmd("wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle"))

-- Brightness controls
hl.bind("XF86MonBrightnessUp", hl.dsp.exec_cmd("brightnessctl set 5%+"))
hl.bind("XF86MonBrightnessDown", hl.dsp.exec_cmd("brightnessctl set 5%-"))

-- Lock screen
hl.bind("SUPER + ALT + L", hl.dsp.exec_cmd("hyprlock"))

-- SCREEN SHOT
hl.bind("SUPER + SHIFT + S", hl.dsp.exec_cmd('grim -g "$(slurp)" ~/hyprland-debug.png'))

-- Anya Forger rofi helpers
hl.bind(mainMod .. " + SHIFT + W", hl.dsp.exec_cmd("rofi -show web"))
hl.bind(mainMod .. " + SHIFT + SLASH", hl.dsp.exec_cmd("~/.config/rofi/scripts/show-keybindings.sh"))

-- Anya Forger Headquarters panel
hl.bind("SUPER + SHIFT + SPACE", hl.dsp.exec_cmd("~/.config/waybar/quick-settings.sh"))
hl.env("HYPRCURSOR_THEME", "cat_cursor")
hl.env("HYPRCURSOR_SIZE", "24")
