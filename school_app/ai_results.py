"""Server-side rendering and decimal arithmetic over actual query results."""
import html
import json
from decimal import Decimal, InvalidOperation
from .ai_workspace import get_result, snapshot


def result_rows(result):
    if isinstance(result.get('rows'),list):
        return result['rows']
    data=result.get('data')
    if isinstance(data,dict):
        return [{'metric':k,'value':v} for k,v in data.items() if not isinstance(v,(dict,list))]
    return []


def render_report(args):
    result=get_result(args.get('result_id'))
    rows=result_rows(result)
    columns=args.get('columns') or (list(rows[0]) if rows else [])
    if not isinstance(columns,list) or not all(isinstance(c,str) for c in columns):
        raise ValueError('ستون‌ها باید فهرست نام ستون‌های نتیجه باشند.')
    if rows and any(c not in rows[0] for c in columns):
        raise ValueError('ستون انتخاب‌شده در نتیجه وجود ندارد.')
    columns=columns[:20]
    headers=args.get('headers') or columns
    if len(headers)!=len(columns):
        raise ValueError('تعداد عنوان‌ها و ستون‌ها برابر نیست.')
    esc=lambda v: html.escape('' if v is None else str(v))
    meta=result['meta']
    parts=['<h4>'+esc(args.get('title','گزارش'))+'</h4>',
           '<p>'+esc(meta['coverage'])+' · '+esc(meta['extracted_at'])+' · '+esc(meta['source'])+'</p>',
           '<p>فیلترها: '+esc(json.dumps(meta.get('effective_filters',meta.get('filters',{})),ensure_ascii=False))+'</p>',
           '<p>جمعیت: '+esc(meta.get('population',meta['coverage']))+' · ردیف‌های نتیجه: '+esc(len(rows))+'</p>',
           '<p>شناسهٔ نتیجه: '+esc(result['result_id'])+'</p>',
           '<table class="agent-table"><thead><tr>'+''.join('<th>'+esc(c)+'</th>' for c in headers)+'</tr></thead><tbody>']
    for row in rows:
        parts.append('<tr>'+''.join('<td>'+esc(row.get(c))+'</td>' for c in columns)+'</tr>')
    parts.append('</tbody></table>')
    return {'content':'\n'.join(parts),'result_id':result['result_id']}


def transform(args):
    source=get_result(args.get('result_id'))
    rows=[dict(r) for r in result_rows(source)]
    key=args.get('filter_column')
    if key:
        if rows and key not in rows[0]: raise ValueError('ستون فیلتر وجود ندارد.')
        value=args.get('filter_value','')
        rows=[r for r in rows if str(r.get(key,''))==str(value)]
    sort=args.get('sort_by')
    if sort:
        if rows and sort not in rows[0]: raise ValueError('ستون مرتب‌سازی وجود ندارد.')
        def sort_key(row):
            value=row.get(sort)
            try:
                number=Decimal(str(value))
                if not number.is_finite(): raise InvalidOperation
                return (0,number)
            except InvalidOperation: return (1,str(value or ''))
        rows.sort(key=sort_key,reverse=bool(args.get('descending',False)))
    meta=dict(source['meta'])
    meta['parent_result_id']=source['result_id']
    meta['row_count']=len(rows)
    meta['original_filters']=source['meta'].get('filters',{})
    # Filtering a page never changes its coverage into a whole-population claim.
    meta['coverage']=source['meta']['coverage']
    return rows,meta


def calculate(args):
    source=get_result(args.get('result_id'))
    rows=result_rows(source)
    operation=args.get('operation','count')
    field=args.get('column')
    if operation=='count': value=len(rows)
    else:
        if rows and field not in rows[0]: raise ValueError('ستون محاسبه در نتیجه نیست.')
        values=[]
        for row in rows:
            raw=row.get(field)
            if raw is None or raw=='': continue
            try:
                number=Decimal(str(raw).replace(',',''))
                if not number.is_finite(): raise InvalidOperation
                values.append(number)
            except InvalidOperation:
                raise ValueError('ستون حاوی مقدار غیرعددی است؛ محاسبه انجام نشد.')
        if not values: value=None
        elif operation=='sum': value=str(sum(values,Decimal(0)))
        elif operation=='average': value=str(sum(values,Decimal(0))/len(values))
        elif operation=='min': value=str(min(values))
        elif operation=='max': value=str(max(values))
        else: raise ValueError('عملیات محاسبه معتبر نیست.')
    return {'operation':operation,'column':field,'value':value,'row_count':len(rows),
            'result_id':source['result_id'],'coverage':source['meta']['coverage'],
            'note':'این محاسبه فقط روی رکوردهای همین نتیجه است؛ برای کل جمعیت از پرس‌وجوی تجمعی استفاده کنید.'}
