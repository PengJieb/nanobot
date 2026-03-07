<!--
 * @Author: PengJie pengjieb@mail.ustc.edu.cn
 * @Date: 2026-03-06 18:32:54
 * @LastEditors: PengJie pengjieb@mail.ustc.edu.cn
 * @LastEditTime: 2026-03-07
 * @FilePath: /nanobot/FEEDBACK.md
 * @Description: 这是默认设置,请设置`customMade`, 打开koroFileHeader查看配置 进行设置: https://github.com/OBKoro1/koro1FileHeader/wiki/%E9%85%8D%E7%BD%AE
-->
## Resolved Issues

✓ [2026-03-07] Fixed: Chinese characters in LLM feedback causing "Could not parse spec from agent response" error
  - Improved JSON extraction in `nanobot/app/builder.py` with robust brace matching
  - Now handles Chinese text before/after JSON, nested braces, and code blocks

## Open Issues

In the app page, the table size is fixed, when the content is too long, the table will create a sidebar to allow user scroll to check content.
