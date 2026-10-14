import os
import re
import numpy as np
import matplotlib.pyplot as plt

# ============================================
# (1) 폴더 설정
# ============================================
input_folder = "step_0"
output_folder = "step_1"
os.makedirs(output_folder, exist_ok=True)

file_list = [f for f in os.listdir(input_folder) if f.endswith(".ini")]
file_list.sort()

print(f"총 {len(file_list)}개의 파일을 처리함\n")


# ============================================
# (2) 이동 중앙값 필터 함수 (현재 포함, 과거 9개)
# ============================================
def moving_median(data, window=10):
    """현재 시점을 포함하여 과거 데이터 window개로 median 계산"""
    filtered = []
    for i in range(len(data)):
        start = max(0, i - window + 1)  # 과거 구간의 시작 인덱스
        end = i + 1                     # 현재 포함
        filtered.append(np.median(data[start:end]))
    return np.array(filtered)


# ============================================
# (3) 파일별 처리
# ============================================
for idx, file_name in enumerate(file_list, start=1):
    input_path = os.path.join(input_folder, file_name)
    print(f"\n[{idx}/{len(file_list)}] : {input_path}")

    data_list = []
    skip_file = False

    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            # [숫자, 숫, ...] 패턴 추출
            match = re.findall(r"\[([0-9, ]+)\]", line)

            if len(match) > 3:
                values_str = match[2]
                try:
                    values = [int(v.strip()) for v in values_str.split(",") if v.strip() != ""]
                except ValueError as e:
                    print(f"⚠️ 변환 오류: {e}")
                    print(f"   → 원본 데이터: {values_str}")
                    skip_file = True
                    break

                # 이동 중앙값 필터 적용
                filtered_values = moving_median(values, window=10)
                data_list.append((values, filtered_values))
            else:
                print("⚠️ 데이터 부족으로 현재 파일 skip")
                skip_file = True
                break

    if skip_file:
        continue

    # ============================================
    # (4) 결과 파일 저장
    # ============================================
    output_path = os.path.join(output_folder, file_name.replace(".ini", "_new.ini"))
    with open(output_path, "w", encoding="utf-8") as out:
        for i, (original, filtered) in enumerate(data_list):
            out.write(f"[{i}]\n")
            out.write(",".join(map(lambda x: str(int(x)), filtered)) + "\n")

    #print(f"✅ Median Filtering 완료 → {output_path}")

    # ============================================
    # (5) 시각화
    # ============================================
    '''
    plt.figure(figsize=(12, 6))
    for i, (original, filtered) in enumerate(data_list):
        plt.plot(original, color='gray', alpha=0.4)
        plt.plot(filtered, linewidth=2, label=f"Region {i}")

    plt.title(f"Median Filtered Data - {file_name}", fontsize=14)
    plt.xlabel("Sample Index")
    plt.ylabel("Value")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.ylim(0, 200)
    plt.show(block=False)
    plt.pause(3)
    plt.close()
    '''
print("\n✅ 모든 파일 처리 및 저장이 완료되었음")
