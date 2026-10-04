import argparse
import csv
from pathlib import Path

from scripts.measure import print_table, save_csv


def read_csv(path):
    with open(path, encoding='utf-8') as file:
        return list(csv.DictReader(file))


def compare_times(small, work):
    work_by_name = {}
    for row in work:
        work_by_name[row['operation']] = row
    if len(small) != len(work):
        raise ValueError('Наборы операций различаются')
    comparison, breakdown = [], []
    for row in small:
        name = row['operation']
        if name not in work_by_name:
            raise ValueError('Наборы операций различаются')
        other = work_by_name[name]
        if row['samples'] != other['samples']:
            raise ValueError('Число повторов различается')
        growth = float(other['p50_ms']) / float(row['p50_ms'])
        comparison.append({
            'operation': name, 'small_p50_ms': row['p50_ms'], 'small_p95_ms': row['p95_ms'],
            'small_max_ms': row['max_ms'], 'work_p50_ms': other['p50_ms'],
            'work_p95_ms': other['p95_ms'], 'work_max_ms': other['max_ms'], 'p50_growth': growth,
        })
        conclusion = 'Остальное'
        if float(other['db_mean_ms']) > float(other['app_mean_ms']):
            conclusion = 'БД'
        detail = other.copy()
        detail['dominant_part'] = conclusion
        breakdown.append(detail)
    return comparison, breakdown


def compare_volumes(folder):
    small = read_csv(folder / 'small' / 'counts.csv')
    work = read_csv(folder / 'work' / 'counts.csv')
    work_by_name = {}
    for row in work:
        work_by_name[row['table']] = row
    volumes = []
    for row in small:
        other = work_by_name[row['table']]
        count = int(row['before'])
        large_count = int(other['before'])
        volumes.append({'table': row['table'], 'small': count, 'work': large_count,
                        'growth': large_count / count,
                        'small_added': int(row['added']), 'work_added': int(other['added'])})
    return volumes


def print_volumes(volumes):
    rows = []
    for row in volumes:
        rows.append([row['table'], row['small'], row['work'], f"{row['growth']:.2f}", row['small_added'], row['work_added']])
    print_table(['Таблица', 'Малое', 'Рабочее', 'Рост, раз', '+ малое', '+ рабочее'], rows)


def print_times(comparison):
    rows = []
    for row in comparison:
        values = [row['operation']]
        for key in ['small_p50_ms', 'small_p95_ms', 'work_p50_ms', 'work_p95_ms']:
            values.append(f'{float(row[key]):.3f}')
        values.append(f'{row["p50_growth"]:.2f}')
        rows.append(values)
    print('Время HTTP, мс')
    print_table(['Операция', 'p50 мал.', 'p95 мал.', 'p50 раб.', 'p95 раб.', 'Рост, раз'], rows)


def print_breakdown(breakdown):
    rows = []
    for row in breakdown:
        rows.append([row['operation'], f"{float(row['server_mean_ms']):.3f}",
                     f"{float(row['db_mean_ms']):.3f}", f"{float(row['app_mean_ms']):.3f}",
                     f"{float(row['sql_count_mean']):.1f}", row['dominant_part']])
    print('Рабочее наполнение: среднее время, мс')
    print_table(['Операция', 'Сервер', 'БД', 'Остальное', 'SQL', 'Преобладает'], rows)
    print('БД: execute, включая драйвер и обмен с PostgreSQL')
    print('Остальное: сервер минус БД, включая подключение и обработку данных')


def compare(output, section):
    folder = Path(output)
    small = read_csv(folder / 'small' / 'summary.csv')
    work = read_csv(folder / 'work' / 'summary.csv')
    comparison, breakdown = compare_times(small, work)
    save_csv(folder / 'comparison.csv', comparison)
    save_csv(folder / 'breakdown.csv', breakdown)
    if section in ['all', 'volumes']:
        volumes = compare_volumes(folder)
        save_csv(folder / 'volumes.csv', volumes)
        print_volumes(volumes)
    if section in ['all', 'times']:
        print_times(comparison)
    if section in ['all', 'breakdown']:
        print_breakdown(breakdown)


def main():
    parser = argparse.ArgumentParser(description='Сравнение двух завершённых прогонов')
    parser.add_argument('--output', default='report_data')
    parser.add_argument('--section', choices=['all', 'volumes', 'times', 'breakdown'], default='all')
    args = parser.parse_args()
    compare(args.output, args.section)


if __name__ == '__main__':
    main()
