-- Evidence Desk 数据库初始化脚本
-- 适用于 seekdb / MySQL 协议兼容数据库

CREATE DATABASE IF NOT EXISTS evidence_desk DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;
USE evidence_desk;

DROP TABLE IF EXISTS records;

CREATE TABLE records (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(500) NOT NULL COMMENT '记录标题',
    content TEXT NOT NULL COMMENT '正文内容',
    source VARCHAR(1000) NOT NULL COMMENT '来源（文件路径、URL、系统名等）',
    record_date DATE NOT NULL COMMENT '记录日期',
    tags VARCHAR(1000) DEFAULT '' COMMENT '标签，逗号分隔',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_record_date (record_date),
    INDEX idx_tags (tags(255))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin
  COMMENT='工作记录表';
