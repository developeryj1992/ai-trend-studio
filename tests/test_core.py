import unittest
import json
import urllib.parse

import app


class CoreTests(unittest.TestCase):
    def test_srt_and_vtt_are_cleaned(self):
        srt = "1\n00:00:01,000 --> 00:00:03,000\n 大家好\n\n2\n00:00:03,000 --> 00:00:05,000\n 今天讲AI工作流"
        self.assertEqual(app.parse_srt_vtt(srt), "大家好 今天讲AI工作流")

        vtt = "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\n这里是字幕"
        self.assertEqual(app.parse_srt_vtt(vtt), "这里是字幕")

    def test_ai_relevance_matches_title_description_and_author(self):
        row = {"title": "普通分享", "description": "讲解大模型应用", "author": "", "extra": {}}
        relevant, matched = app.is_ai_relevant(row, ["AI", "大模型"])
        self.assertTrue(relevant)
        self.assertIn("大模型", matched)

    def test_local_summary_extracts_points_actions_and_risks(self):
        text = (
            "这场直播的核心结论是AI智能体必须绑定业务流程。"
            "第一个关键点是先整理数据，再评估模型。"
            "第二个价值点是把客服回复效率提升百分之三十。"
            "建议下一步先用小范围试点验证成本。"
            "需要注意隐私合规风险，避免上传客户敏感数据。"
        )
        result = app.local_summary("AI智能体落地", text)
        self.assertEqual(result["headline"], "AI智能体落地")
        self.assertTrue(any("业务流程" in point for point in result["key_points"]))
        self.assertTrue(any("试点" in action for action in result["action_items"]))
        self.assertTrue(any("合规" in risk for risk in result["risks"]))

    def test_llm_json_normalizer_accepts_fenced_json(self):
        raw = '```json\n{"headline":"AI周报","key_points":["模型成本下降"],"keywords":["AI"],"action_items":[],"risks":[]}\n```'
        result = app.normalize_llm_json(raw, app.local_summary("AI周报", "模型成本下降"))
        self.assertEqual(result["engine"], "llm")
        self.assertEqual(result["headline"], "AI周报")
        self.assertEqual(result["key_points"], ["模型成本下降"])

    def test_chinese_metric_parser(self):
        self.assertEqual(app.parse_cn_number("3639 万热度"), 36390000)
        self.assertEqual(app.parse_cn_number("851 万热度"), 8510000)
        self.assertEqual(app.parse_cn_number("1234 热度"), 1234)
        self.assertEqual(app.parse_cn_number("invalid"), 0)

    def test_douyin_live_payload_is_normalized(self):
        payload = {
            "status_code": 0,
            "data": [
                {
                    "room": {
                        "web_rid": "541395769307",
                        "id_str": "7695391322215041819",
                        "title": "AI Agent 落地连线",
                        "status": 2,
                        "owner": {"nickname": "AI 主播"},
                        "stats": {"user_count_str": "1.2万"},
                        "linkmic_status": 1,
                    }
                }
            ],
        }
        rows = app.parse_douyin_live_payload(payload)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["platform"], "douyin")
        self.assertEqual(rows[0]["kind"], "live_room")
        self.assertEqual(rows[0]["url"], "https://live.douyin.com/541395769307")
        self.assertEqual(rows[0]["heat"], 12000)
        self.assertEqual(rows[0]["extra"]["mode"], "multi")

    def test_douyin_live_search_html_parses_encoded_json_and_ignores_invalid(self):
        payload = {
            "rooms": [
                {"web_rid": "386832142290", "title": "大模型应用直播", "author": {"nickname": "研究员"}},
                {"web_rid": "386832142290", "title": "重复房间"},
            ]
        }
        encoded = urllib.parse.quote(json.dumps(payload, ensure_ascii=False))
        html_text = (
            '<script type="application/json" id="test">not-json</script>'
            f'<script type="application/json" id="LIVE_SSR_DATA_ID">{encoded}</script>'
        )
        rows = app.parse_douyin_live_search_html(html_text)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "大模型应用直播")
        self.assertEqual(rows[0]["author"], "研究员")
        self.assertEqual(app.parse_douyin_live_search_html("<script>{broken</script>"), [])

    def test_public_state_masks_api_key(self):
        state = app.public_state()
        self.assertIn(state["settings"]["llm"].get("api_key"), (None, "", "********"))


if __name__ == "__main__":
    unittest.main()
