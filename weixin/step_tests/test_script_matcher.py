"""Step-test: verify script matcher against real and simulated ASR output."""
import sys
sys.stdout.reconfigure(encoding="utf-8")

from script_matcher import match_query, get_index


def main():
    idx = get_index()
    print(f"Loaded {len(idx.lines)} dialog lines.\n")

    # ---- Test 1: heavily corrupted ASR of a known line ----
    # Original: 哥哥我走还不行吗？不要再打我了，我怕！
    # Simulated ASR with homophone errors
    asr1 = "咯咯我走还不行吗不要再打我了哦怕"
    print(f"{'='*60}")
    print(f"Test 1: Simulated homophone errors")
    print(f"  ASR : {asr1}")
    print(f"  Orig: 哥哥我走还不行吗？不要再打我了，我怕！")
    results = match_query(asr1, top_n=3)
    for j, r in enumerate(results, 1):
        print(f"  #{j} combined={r['similarity_score']:.2%}  "
              f"pinyin={r['pinyin_score']:.2%}  char={r['char_score']:.2%}")
        print(f"      [{r['episode']}][{r['scene']}] {r['character']}")
        print(f"      {r['script_text'][:80]}")
    if not results:
        print("  (no match)")
    print()

    # ---- Test 2: another known line with errors ----
    # Original: 这一巴掌下去，我跟你们顾家那点单薄的血缘，可就真断了。
    asr2 = "这一巴掌下去我跟你们顾佳那点丹柏的血缘可真断了"
    print(f"{'='*60}")
    print(f"Test 2: Homophone errors on line 2")
    print(f"  ASR : {asr2}")
    print(f"  Orig: 这一巴掌下去，我跟你们顾家那点单薄的血缘，可就真断了。")
    results = match_query(asr2, top_n=3)
    for j, r in enumerate(results, 1):
        print(f"  #{j} combined={r['similarity_score']:.2%}  "
              f"pinyin={r['pinyin_score']:.2%}  char={r['char_score']:.2%}")
        print(f"      [{r['episode']}][{r['scene']}] {r['character']}")
        print(f"      {r['script_text'][:80]}")
    if not results:
        print("  (no match)")
    print()

    # ---- Test 3: short snippet ----
    # Original: 你们顾家这么有钱
    asr3 = "你们顾佳这么有钱"
    print(f"{'='*60}")
    print(f"Test 3: Short snippet")
    print(f"  ASR : {asr3}")
    results = match_query(asr3, top_n=3)
    for j, r in enumerate(results, 1):
        print(f"  #{j} combined={r['similarity_score']:.2%}  "
              f"pinyin={r['pinyin_score']:.2%}  char={r['char_score']:.2%}")
        print(f"      [{r['episode']}][{r['scene']}] {r['character']}")
        print(f"      {r['script_text'][:80]}")
    if not results:
        print("  (no match)")
    print()

    # ---- Test 4: very short query ----
    asr4 = "滚现在就滚"
    print(f"{'='*60}")
    print(f"Test 4: Very short query")
    print(f"  ASR : {asr4}")
    results = match_query(asr4, top_n=3)
    for j, r in enumerate(results, 1):
        print(f"  #{j} combined={r['similarity_score']:.2%}  "
              f"pinyin={r['pinyin_score']:.2%}  char={r['char_score']:.2%}")
        print(f"      [{r['episode']}][{r['scene']}] {r['character']}")
        print(f"      {r['script_text'][:80]}")
    if not results:
        print("  (no match)")
    print()

    # ---- Test 5: unrelated content (should get low/no match) ----
    asr5 = "宗也配说普度众生这倒是尤其胆气真想看看他如何收场"
    print(f"{'='*60}")
    print(f"Test 5: Unrelated content (expect low scores)")
    print(f"  ASR : {asr5}")
    results = match_query(asr5, top_n=3, min_pinyin_score=0.45)
    for j, r in enumerate(results, 1):
        print(f"  #{j} combined={r['similarity_score']:.2%}")
        print(f"      {r['script_text'][:60]}")
    if not results:
        print("  (no match, as expected)")
    print()


if __name__ == "__main__":
    main()
