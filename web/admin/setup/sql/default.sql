
CREATE TABLE IF NOT EXISTS `backup` (
  `id` INTEGER PRIMARY KEY AUTOINCREMENT,
  `pid` INTEGER,
  `type` INTEGER,
  `name` TEXT,
  `filename` TEXT,
  `size` INTEGER,
  `add_time` TEXT
);

CREATE TABLE IF NOT EXISTS `binding` (
  `id` INTEGER PRIMARY KEY AUTOINCREMENT,
  `pid` INTEGER,
  `port` INTEGER,
  `domain` TEXT,
  `path` TEXT,
  `add_time` TEXT
);


CREATE TABLE IF NOT EXISTS `crontab` (
  `id` INTEGER PRIMARY KEY AUTOINCREMENT,
  `name` TEXT,
  `type` TEXT,
  `where1` TEXT,
  `where_hour` INTEGER,
  `where_minute` INTEGER,
  `echo` TEXT,
  `status` INTEGER DEFAULT '1',
  `save` INTEGER DEFAULT '3',
  `backup_to` TEXT DEFAULT 'off', 
  `sname` TEXT,
  `sbody` TEXT,
  `stype` TEXT,
  `url_address` TEXT,
  `attr` TEXT DEFAULT '',
  `day_type` INTEGER DEFAULT 0,
  `last_run_time` TEXT,
  `add_time` TEXT,
  `update_time` TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS crontab_name_idx ON crontab(name);


CREATE TABLE IF NOT EXISTS `firewall` (
  `id` INTEGER PRIMARY KEY AUTOINCREMENT,
  `port` TEXT,
  `protocol` TEXT DEFAULT 'tcp',
  `status` INTEGER DEFAULT '1',
  `type` TEXT DEFAULT 'port',
  `ps` TEXT,
  `add_time` TEXT,
  `update_time` TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS firewall_port_idx ON firewall(port);

INSERT INTO `firewall` (`id`, `port`, `protocol`, `ps`, `add_time`, `update_time`) VALUES
(1, '80',  'tcp', '网站默认端口', '0000-00-00 00:00:00','0000-00-00 00:00:00'),
(2, '443', 'tcp/udp', 'HTTPS', '0000-00-00 00:00:00','0000-00-00 00:00:00');

CREATE TABLE IF NOT EXISTS `logs` (
  `id` INTEGER PRIMARY KEY AUTOINCREMENT,
  `type` TEXT,
  `log` TEXT,
  `uid` INTEGER DEFAULT '1',
  `add_time` TEXT
);

CREATE TABLE IF NOT EXISTS `sites` (
  `id` INTEGER PRIMARY KEY AUTOINCREMENT,
  `name` TEXT,
  `path` TEXT,
  `status` TEXT,
  `index` TEXT,
  `type_id` INTEGER,
  `ps` TEXT,
  `edate` TEXT,
  `ssl_effective_date` TEXT,
  `ssl_expiration_date` TEXT,
  `add_time` TEXT,
  `update_time` TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS sites_name_idx ON sites(name);

CREATE TABLE IF NOT EXISTS `site_types` (
  `id` INTEGER PRIMARY KEY AUTOINCREMENT,
  `name` TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS site_types_name_idx ON site_types(name);


CREATE TABLE IF NOT EXISTS `domain` (
  `id` INTEGER PRIMARY KEY AUTOINCREMENT,
  `pid` INTEGER,
  `name` TEXT,
  `port` INTEGER,
  `main` INTEGER DEFAULT '0',
  `add_time` TEXT
);

CREATE TABLE IF NOT EXISTS `users` (
  `id` INTEGER PRIMARY KEY AUTOINCREMENT,
  `name` TEXT,
  `password` TEXT,
  `login_ip` TEXT,
  `login_time` TEXT,
  `phone` TEXT,
  `email` TEXT,
  `add_time` TEXT,
  `update_time` TEXT
);

CREATE TABLE IF NOT EXISTS `tasks` (
  `id` INTEGER PRIMARY KEY AUTOINCREMENT,
  `name` 			TEXT,
  `type`			TEXT,
  `start` 	  INTEGER,
  `end` 	    INTEGER,
  `cmd` 	    TEXT,
  `status`    INTEGER,
  `add_time`  TEXT
);

CREATE TABLE IF NOT EXISTS `temp_login` (
  `id`  INTEGER PRIMARY KEY AUTOINCREMENT,
  `token` REAL,
  `salt`  REAL,
  `state` INTEGER,
  `login_time`  INTEGER,
  `login_addr`  REAL,
  `logout_time` INTEGER,
  `expire`  INTEGER,
  `add_time` TEXT
);

CREATE TABLE IF NOT EXISTS `panel` (
  `id` INTEGER PRIMARY KEY AUTOINCREMENT,
  `title` TEXT,
  `url` TEXT,
  `username` TEXT,
  `password` TEXT,
  `click` INTEGER,
  `add_time` TEXT
);

CREATE TABLE IF NOT EXISTS `app` (
  `id` INTEGER PRIMARY KEY AUTOINCREMENT,
  `name` TEXT,
  `app_id` TEXT,
  `app_secret` TEXT,
  `white_list` TEXT,
  `status` INTEGER,
  `add_time` TEXT,
  `update_time` TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS app_name_idx ON app(name);
CREATE UNIQUE INDEX IF NOT EXISTS app_id_idx ON app(app_id);

CREATE TABLE IF NOT EXISTS `option` (
  `id` INTEGER PRIMARY KEY AUTOINCREMENT,
  `name` TEXT,
  `type` TEXT,
  `value` TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS option_name_idx ON option(name);

CREATE INDEX IF NOT EXISTS domain_pid_idx ON domain(pid);
CREATE INDEX IF NOT EXISTS domain_name_idx ON domain(name);

CREATE INDEX IF NOT EXISTS binding_pid_idx ON binding(pid);
CREATE INDEX IF NOT EXISTS binding_domain_idx ON binding(domain);

CREATE INDEX IF NOT EXISTS backup_pid_type_idx ON backup(pid, type);

CREATE INDEX IF NOT EXISTS logs_type_idx ON logs(type);
CREATE INDEX IF NOT EXISTS logs_add_time_idx ON logs(add_time);

CREATE INDEX IF NOT EXISTS tasks_status_idx ON tasks(status);
