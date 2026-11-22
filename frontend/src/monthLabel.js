// Server calendar month, with no browser timezone conversion.
export function monthLabel(value,suffix,fallback){
  const match=typeof value==='string' && value.match(/^(\d{4})-(\d{2})-01$/)
  if(!match || Number(match[1])<1 || Number(match[2])<1 || Number(match[2])>12)return fallback
  return ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][Number(match[2])-1]+' '+suffix
}
