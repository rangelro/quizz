# Quizz

Quiz estilo Kahoot para rede local. Um apresentador projeta as perguntas na tela grande e os jogadores respondem pelo celular. Só usa a biblioteca padrão do Python, então não precisa instalar nada.

## Como rodar

Requisito: Python 3.8 ou mais recente.

```bash
python3 server.py
```

O terminal mostra dois endereços:

```
Jogadores, acessem: http://192.168.0.10:8000
Apresentador (tela grande): http://localhost:8000/?key=XXXXXXXX
```

1. **Apresentador:** abra o link com `?key=...` no computador ligado ao projetor. Só quem tem essa chave consegue avançar as perguntas.
2. **Jogadores:** entram pelo QR code exibido na tela ou digitando o endereço. Os celulares precisam estar **na mesma rede Wi-Fi** do computador.
3. O apresentador clica para começar e para avançar entre pergunta → resultado → próxima pergunta.

Dicas:
- Se os celulares não conseguirem acessar, libere a porta 8000 no firewall (ex.: Fedora: `sudo firewall-cmd --add-port=8000/tcp`).
- A chave do apresentador fica salva em `.host_key` e continua a mesma quando o servidor é reiniciado. Para gerar outra, apague o arquivo.
- Para mudar a porta ou o tempo padrão, edite `PORT` e `TIME_LIMIT` no início do `server.py`.
- Reiniciar o servidor zera o jogo (jogadores e pontuação).

## Como colocar as perguntas

As perguntas ficam em `questions.json`, uma lista onde cada item é uma pergunta:

```json
[
  {
    "q": "Qual é a capital do Brasil?",
    "options": ["São Paulo", "Brasília", "Rio de Janeiro", "Salvador"],
    "answer": 1
  },
  {
    "q": "(Sim ou Não) O Python é uma linguagem interpretada?",
    "options": ["Sim", "Não"],
    "answer": 0,
    "time": 20
  }
]
```

| Campo     | Obrigatório | Descrição |
|-----------|-------------|-----------|
| `q`       | sim | Texto da pergunta. |
| `options` | sim | De 2 a 4 alternativas. |
| `answer`  | sim | Índice da alternativa correta, **começando em 0** (0 = primeira, 1 = segunda...). |
| `time`    | não | Tempo em segundos para essa pergunta. Padrão: 45. |

As perguntas aparecem na ordem do arquivo. Depois de editar, reinicie o servidor. Se alguma pergunta estiver errada (menos de 2 ou mais de 4 opções, ou `answer` fora do intervalo), o servidor não sobe e mostra qual é a pergunta com problema.

Atenção ao JSON: use aspas duplas e coloque vírgula entre as perguntas, mas não depois da última.

## Pontuação

Resposta certa vale de 500 a 1000 pontos: quanto mais rápido, mais pontos. Resposta errada ou sem resposta vale 0. A pergunta fecha quando o tempo acaba ou quando todos responderem.

## Testes

```bash
python3 test_quiz.py
```
