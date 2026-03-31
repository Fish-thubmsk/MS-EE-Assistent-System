新数学JSON 目录说明（交付版）

1) final\
   - 最终可交付数据（推荐直接使用）
   - 文件：
     - kmath_questions1_final.json  （数学一）
     - kmath_questions2_final.json  （数学二）
     - kmath_questions3_final.json  （数学三）
   - 字段最精简，不含 source_question_id / paper_id / crawled_at

2) docs\
   - 文档说明
   - 文件：
     - 数据库设计说明_考研数学题库.md

3) scripts\
   - 脚本文件
   - 文件：
     - scrape_kmath_questions.py

4) slim\
   - 中间瘦身版（保留 source_question_id，便于追溯）
   - 文件：
     - kmath_questions1_slim.json
     - kmath_questions2_slim.json
     - kmath_questions3_slim.json

5) raw\
   - 原始导出数据与样例
   - 文件：
     - kmath_questions1.json
     - kmath_questions2.json
     - kmath_questions3.json
     - kmath_questions_sample.json

6) capture\
   - 抓包分析文件
   - 文件：
     - 考研数学.har

------------------------------------------------------------
最终提交建议：
- 数据：使用 final\ 下 3 个 *_final.json
- 说明：附带 docs\数据库设计说明_考研数学题库.md
------------------------------------------------------------
