import os
import re
import numpy as np

# -----------------------------
# (1) 폴더 설정
# -----------------------------
input_folder = "step_1"
output_folder = "step_2"

os.makedirs(output_folder, exist_ok=True)

# _filtered.txt 파일만 대상
file_list = [f for f in os.listdir(input_folder) if f.endswith("_new.ini")]
file_list.sort()

print(f"총 {len(file_list)}개의 파일을 처리합니다.\n")

# -----------------------------
# (2) 파일별 처리
# -----------------------------
for file_name in file_list:
    file_path = os.path.join(input_folder, file_name)
    print(f"\n현재 파일: {file_path}")

    # 영역별 데이터 저장 딕셔너리
    region_data = {}
    current_region = None

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            # [번호] 형태 탐지
            region_match = re.match(r"\[(\d+)\]", line)
            if region_match:
                current_region = int(region_match.group(1))
                region_data[current_region] = []
                continue

            # 숫자 리스트 탐지
            if current_region is not None and re.match(r"^-?\d+(,[-\d\s]*)*$", line):
                try:
                    values = [int(v.strip()) for v in line.split(",") if v.strip() != ""]
                    region_data[current_region].extend(values)
                except ValueError:
                    pass

    if not region_data:
        print("⚠️ 데이터가 없습니다. (skip)")
        continue

    # -----------------------------
    # (3) 영역별 데이터 정렬 및 길이 확인
    # -----------------------------
    region_count = len(region_data)
    max_len = max(len(v) for v in region_data.values())
    print(f"▶ {region_count}개 영역, 최대 길이 {max_len} 데이터")

    # -----------------------------
    # (4) 순번별로 데이터 추출 후 파일 저장
    # -----------------------------
    for idx in range(max_len):
        values_at_idx = []
        for region_idx in sorted(region_data.keys()):
            region_values = region_data[region_idx]
            if idx < len(region_values):
                values_at_idx.append(region_values[idx])
            else:
                values_at_idx.append(np.nan)  # 없는 값은 NaN 처리

        # 파일로 저장
        output_name = f"{os.path.splitext(file_name)[0]}_{idx+1:04d}.ini"
        output_path = os.path.join(output_folder, output_name)

        with open(output_path, "w", encoding="utf-8") as out:
            out.write(",".join(map(lambda x: "NaN" if np.isnan(x) else str(int(x)), values_at_idx)) + "\n")

        print(f"  ➕ {output_name} 저장 완료 ({len(values_at_idx)}개 값)")

print("\n✅ 모든 파일의 순번별 데이터 분리 및 저장이 완료되었습니다.")
