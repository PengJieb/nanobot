<!--
 * @Author: PengJie pengjieb@mail.ustc.edu.cn
 * @Date: 2026-03-06 18:32:54
 * @LastEditors: PengJie pengjieb@mail.ustc.edu.cn
 * @LastEditTime: 2026-03-06 18:31:13
 * @FilePath: /nanobot/FEEDBACK.md
 * @Description: 这是默认设置,请设置`customMade`, 打开koroFileHeader查看配置 进行设置: https://github.com/OBKoro1/koro1FileHeader/wiki/%E9%85%8D%E7%BD%AE
-->
Add theme change function for the entire web and applications' page.
Make sure all items in application page is well aligned: like the title, the input box, the button, etc.
Refer to refer_html_page.html to render the entire web page: include chat, skills, Apps, etc.
For application json file, add an optional key word: color, which the nano bot will randomly select one color scheme file under the assert/color_theme folder and send to the LLM to assign the color of each item in the application page (like the title, the input box, the button, etc.).
