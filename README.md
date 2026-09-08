# PyRadio

Player de rádios online com interface gráfica em PySide6 (Qt) e reprodução de áudio via VLC.

## Tecnologias

- **Python 3** — linguagem da aplicação.
- **PySide6** — bindings Qt para a interface gráfica (`QWidget`, `QComboBox`, `QSlider`, etc.).
- **python-vlc** — bindings do libVLC para decodificar e reproduzir os streams de áudio.
- **libVLC (sistema)** — dependência nativa não instalável via pip (`libvlc5`, `libvlc-bin`, `vlc-plugin-base`).
- **Radio-Browser API** (`de1.api.radio-browser.info`) — fonte pública dos dados de países e estações de rádio.

## Arquitetura

Todo o código está em [pyradio.py](pyradio.py), organizado em duas classes principais:

### `RadioApp(QWidget)`
Janela principal e ponto central de toda a lógica da aplicação:

- **UI** (`setup_ui`): monta os controles — combo de país, campo de busca, combo de rádios, botões Play/Pause/Stop, slider de volume e label de status.
- **Dados remotos**: `load_countries()` e `load_radios()` fazem requisições HTTP síncronas (`urllib.request`) à Radio-Browser API para obter, respectivamente, a lista de países e as estações filtradas por país (ordenadas por popularidade de cliques). `register_click()` notifica a API quando uma estação é tocada.
- **Reprodução**: `play()` dispara uma `threading.Thread` (`_play_stream`) que cria a mídia no VLC (`vlc.Instance`/`media_player_new`) e inicia a reprodução, evitando bloquear a UI. Sinais Qt (`playback_started`, `playback_error`) são usados para sincronizar o resultado da thread com a thread principal da UI.
- **Controle de estado**: `pause()`, `stop()` e `set_volume()` interagem diretamente com o `player` do VLC. Um `QTimer` (`update_status`) verifica periodicamente o estado do player para detectar quedas de stream.
- **Log**: mensagens são acumuladas em `self.log_messages` e exibidas em uma janela auxiliar (`LogWindow`), aberta com duplo clique no label "Country".

### `LogWindow(QDialog)`
Janela simples de log (somente leitura), usada para depuração e exibição de eventos de reprodução.

### Fluxo de dados

```
Radio-Browser API ──HTTP/JSON──> load_countries()/load_radios()
                                        │
                                        ▼
                              RadioApp (estado + UI)
                                        │
                          thread separada (_play_stream)
                                        │
                                        ▼
                                  libVLC (player)
                                        │
                                        ▼
                                 saída de áudio
```

A interação do usuário (seleção de país/rádio, busca, play/pause/stop, volume) atualiza o estado em `RadioApp`, que por sua vez comanda o `player` do VLC. A comunicação entre a thread de rede/reprodução e a thread principal da UI é feita exclusivamente via sinais Qt (`Signal`), respeitando o modelo de threads do Qt.

## Instalação

Requer as bibliotecas de sistema do VLC (não instaláveis via pip):

```bash
sudo apt install libvlc5 libvlc-bin vlc-plugin-base
```

Crie o ambiente virtual e instale as dependências Python:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Uso

```bash
python pyradio.py
```

1. Selecione o país desejado — a lista de rádios é carregada automaticamente.
2. Use o campo de busca para filtrar rádios por nome.
3. Selecione uma rádio na lista para iniciar a reprodução automaticamente.
4. Use os botões Play/Pause/Stop e o slider de volume para controlar a reprodução.
5. Dê duplo clique no label "Country" para abrir a janela de logs.
