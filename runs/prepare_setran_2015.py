from collections import defaultdict
from copy import deepcopy
from pathlib import Path
from xml.etree.ElementTree import Comment, Element, ElementTree, indent, parse


# Tabela 9, Pando e Fuchs (UTFPR, 2015). A via inicial determina a fase de referência.
rows = [
    (325, 62, ('Chile', 'Brigadeiro Franco'), (46, 34), ('1721952587',)),
    (532, 46, ('Chile', 'Lamenha Lins'), (52, 28), ('978827164',)),
    (175, 3, ('Chile', 'Westphalen'), (43, 37), ('3218088943',)),
    (176, 71, ('Chile', 'Marechal Floriano'), (40, 38), ('269274518', '269274519')),
    (661, 66, ('Conselheiro Dantas', 'Brigadeiro Franco'), (42, 38), ('668980108',)),
    (662, 70, ('Conselheiro Dantas', 'Lamenha Lins'), (44, 36), ('668980111',)),
    (663, 17, ('Conselheiro Dantas', '24 de Maio'), (38, 42), ('267193280',)),
    (664, 30, ('Alferes Poli', 'Conselheiro Dantas'), (33, 47), ('269285955',)),
    (665, 32, ('Westphalen', 'Conselheiro Dantas'), (25, 55), ('865726655',)),
    (319, 82, ('Kennedy', 'Brigadeiro Franco'), (56, 24), ('267193378', '668980106')),
    (179, 17, ('Kennedy', '24 de Maio'), (53, 27), ('267193281', '267193282')),
    (178, 26, ('Kennedy', 'Westphalen'), (39, 41), ('267193381', '571309055')),
    (177, 49, ('Kennedy', 'Conselheiro Dantas', 'Marechal Floriano'), (29, 19, 23), ('267419701',)),
    (534, 85, ('Piauí', 'Brigadeiro Franco'), (40, 40), ('372407124',)),
]

net = parse('data/cache/network/curitiba.net.xml').getroot()
edge_names = {e.get('id'): e.get('name', '') for e in net.findall('edge')}
logics = {p.get('id'): p for p in net.findall('tlLogic')}
links = defaultdict(list)
for con in net.findall('connection'):
    if con.get('tl'):
        links[con.get('tl')].append((int(con.get('linkIndex')), edge_names[con.get('from')]))

additional = Element('additional')
additional.append(Comment(' Adaptação parcial da Tabela 9 de Pando e Fuchs, UTFPR (2015), plano SETRAN SA-14 das 7 h às 9 h. '))
additional.append(Comment(' Estados e transições da malha SUMO, verdes proporcionais aos dados históricos e ciclo de 90 s. '))
additional.append(Comment(' Fonte https://repositorio.utfpr.edu.br/jspui/bitstream/1/8124/1/CT_ENGCOMP_2015_1_09.pdf '))

for number, offset, streets, green_published, signals in rows:
    for signal in signals:
        logic = deepcopy(logics[signal])
        logic.set('programID', 'setran-sa14-2015')
        phases = logic.findall('phase')
        duration = [int(float(p.get('duration'))) for p in phases]
        assert sum(duration) == 90, (signal, duration)
        stages = {name: [] for name in streets}
        for i, phase in enumerate(phases):
            lamps = phase.get('state')
            if any(lamp in 'yYuU' for lamp in lamps):
                continue
            active = {name for name in streets for index, incoming in links[signal]
                      if name in incoming and lamps[index] in 'Gg'}
            if len(active) == 1:
                stages[active.pop()].append(i)
            else:
                assert not active, (signal, lamps, active)
        assert all(stages.values()), (signal, stages)
        representative = [max(stages[name], key=duration.__getitem__) for name in streets]
        available = sum(duration[i] for indices in stages.values() for i in indices)
        allocated = [round(available * weight / sum(green_published)) for weight in green_published]
        allocated[-1] += available - sum(allocated)
        for name, stage, total in zip(streets, representative, allocated):
            duration[stage] = total - sum(duration[i] for i in stages[name] if i != stage)
            assert duration[stage] >= 7, (signal, stages, duration)
            phases[stage].set('duration', str(duration[stage]))
        assert sum(duration) == 90
        reference = stages[streets[0]][0]
        offset_sumo = (offset - sum(duration[:reference])) % 90
        logic.set('offset', str(offset_sumo))
        additional.append(Comment(f' SETRAN {number}. Verde de referência {streets[0]}. '
                                  f'Defasagem publicada {offset} s. Verdes publicados {green_published} s. '))
        additional.append(logic)
        print(number, signal, stages, green_published, allocated, offset_sumo)

indent(additional)
ElementTree(additional).write(Path('config/signals/setran-reboucas-2015.add.xml'), encoding='utf-8', xml_declaration=True)
