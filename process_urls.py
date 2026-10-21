import argparse
import json
from pathlib import Path

from url_utils import english_maps_url

input_file = 'input/hong_kong_place_ids_and_urls_progress2.jsonl'
output_file = 'input/hong_kong_place_ids_and_urls_progress2_en.jsonl'


def process_urls(source=input_file, destination=output_file):
    if Path(source).resolve() == Path(destination).resolve():
        raise ValueError('输入和输出文件不能相同')
    with open(source, encoding='utf-8-sig') as infile:
        Path(destination).parent.mkdir(parents=True, exist_ok=True)
        with open(destination, 'w', encoding='utf-8') as outfile:
            for line_number, line in enumerate(infile, 1):
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    if not isinstance(data, dict):
                        raise ValueError('每行必须是 JSON 对象')
                    data['Maps_url'] = english_maps_url(data.get('Maps_url') or data.get('url'))
                    if 'url' in data:
                        data['url'] = data['Maps_url']
                    outfile.write(json.dumps(data, ensure_ascii=False) + '\n')
                except (ValueError, TypeError) as exc:
                    print(f'Skipping malformed input at line {line_number}: {exc}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='为 Maps_url/url 设置英文界面参数')
    parser.add_argument('input_file', nargs='?', default=input_file)
    parser.add_argument('output_file', nargs='?', default=output_file)
    args = parser.parse_args()
    process_urls(args.input_file, args.output_file)
