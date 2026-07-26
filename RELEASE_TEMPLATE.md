### 🚀 御风面板BtSimple 更新说明

- **插件发布**：全新推出「PostgreSQL 容器化管理插件 1.0」，支持一键部署基于 Docker 的 PostgreSQL 隔离实例，支持动态修改内外网访问边界（0.0.0.0/127.0.0.1 瞬间重构切换）；内置全自动化灾备体系，每日/每周定时无锁热备，支持手动还原指定备份。
  ![pg_docker](https://raw.githubusercontent.com/clhome/bt_simple/master/%E6%96%87%E6%A1%A3/%E5%BE%A1%E9%A3%8E%E9%9D%A2%E6%9D%BF%E8%AF%B4%E6%98%8E%E4%B9%A6/%E8%AF%B4%E6%98%8E%E4%B9%A6.assets/pg_docker.webp)
- **插件更新**：完成「御风系统优化插件 1.0」，并优化其显示效果。

![御风系统优化](https://raw.githubusercontent.com/clhome/bt_simple/master/%E6%96%87%E6%A1%A3/%E5%BE%A1%E9%A3%8E%E9%9D%A2%E6%9D%BF%E8%AF%B4%E6%98%8E%E4%B9%A6/%E8%AF%B4%E6%98%8E%E4%B9%A6.assets/linux_sys_opt.webp)

- **功能优化**：
  - PostgreSQL 容器化管理插件 (pg-docker) 备份机制全面增强，支持自动/手动备份独立存储、增加备份注释、支持备份文件直接下载、列表直观显示自动备份状态，并加入容器关闭时自动跳过备份的容错处理。
  - 防火墙端口列表支持升序/降序排列（兼容端口范围的排序）。
  - 优化软件商店的插件排序规则以提升查找效率，并适当增加了“软件名称”的列宽以优化UI显示体验。
  - 计划任务执行日志中增加显示对应的任务名称；优化文件管理中长文件名及软链接的显示，并在文件菜单中新增复制完整路径的功能。
- **问题修复**：修复 Docker 镜像获取时的解析出错问题。
