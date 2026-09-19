"""Nombres en espanol de las clases que reconoce el modelo.

El modelo trabaja internamente con los nombres del conjunto COCO (en ingles):
esos son los que se guardan en la base de datos, porque son la clave estable.
Todo lo que ve una persona —alertas, tablas, etiquetas sobre el video— pasa por
aqui para mostrarse en espanol y bien escrito en singular o plural.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Tuple

# clase COCO -> (singular, plural)
ES: Dict[str, Tuple[str, str]] = {
    "person": ("persona", "personas"),
    "bicycle": ("bicicleta", "bicicletas"),
    "car": ("auto", "autos"),
    "motorcycle": ("motocicleta", "motocicletas"),
    "airplane": ("avion", "aviones"),
    "bus": ("autobus", "autobuses"),
    "train": ("tren", "trenes"),
    "truck": ("camion", "camiones"),
    "boat": ("bote", "botes"),
    "traffic light": ("semaforo", "semaforos"),
    "fire hydrant": ("hidrante", "hidrantes"),
    "stop sign": ("senal de alto", "senales de alto"),
    "parking meter": ("parquimetro", "parquimetros"),
    "bench": ("banca", "bancas"),
    "bird": ("ave", "aves"),
    "cat": ("gato", "gatos"),
    "dog": ("perro", "perros"),
    "horse": ("caballo", "caballos"),
    "sheep": ("oveja", "ovejas"),
    "cow": ("vaca", "vacas"),
    "elephant": ("elefante", "elefantes"),
    "bear": ("oso", "osos"),
    "zebra": ("cebra", "cebras"),
    "giraffe": ("jirafa", "jirafas"),
    "backpack": ("mochila", "mochilas"),
    "umbrella": ("paraguas", "paraguas"),
    "handbag": ("bolso", "bolsos"),
    "tie": ("corbata", "corbatas"),
    "suitcase": ("maleta", "maletas"),
    "frisbee": ("disco volador", "discos voladores"),
    "skis": ("esquis", "esquis"),
    "snowboard": ("tabla de snowboard", "tablas de snowboard"),
    "sports ball": ("pelota", "pelotas"),
    "kite": ("cometa", "cometas"),
    "baseball bat": ("bate", "bates"),
    "baseball glove": ("guante de beisbol", "guantes de beisbol"),
    "skateboard": ("patineta", "patinetas"),
    "surfboard": ("tabla de surf", "tablas de surf"),
    "tennis racket": ("raqueta", "raquetas"),
    "bottle": ("botella", "botellas"),
    "wine glass": ("copa", "copas"),
    "cup": ("taza", "tazas"),
    "fork": ("tenedor", "tenedores"),
    "knife": ("cuchillo", "cuchillos"),
    "spoon": ("cuchara", "cucharas"),
    "bowl": ("tazon", "tazones"),
    "banana": ("platano", "platanos"),
    "apple": ("manzana", "manzanas"),
    "sandwich": ("sandwich", "sandwiches"),
    "orange": ("naranja", "naranjas"),
    "broccoli": ("brocoli", "brocolis"),
    "carrot": ("zanahoria", "zanahorias"),
    "hot dog": ("hot dog", "hot dogs"),
    "pizza": ("pizza", "pizzas"),
    "donut": ("dona", "donas"),
    "cake": ("pastel", "pasteles"),
    "chair": ("silla", "sillas"),
    "couch": ("sofa", "sofas"),
    "potted plant": ("planta", "plantas"),
    "bed": ("cama", "camas"),
    "dining table": ("mesa", "mesas"),
    "toilet": ("inodoro", "inodoros"),
    "tv": ("pantalla", "pantallas"),
    "laptop": ("laptop", "laptops"),
    "mouse": ("mouse", "mouses"),
    "remote": ("control remoto", "controles remotos"),
    "keyboard": ("teclado", "teclados"),
    "cell phone": ("celular", "celulares"),
    "microwave": ("microondas", "microondas"),
    "oven": ("horno", "hornos"),
    "toaster": ("tostadora", "tostadoras"),
    "sink": ("lavabo", "lavabos"),
    "refrigerator": ("refrigerador", "refrigeradores"),
    "book": ("libro", "libros"),
    "clock": ("reloj", "relojes"),
    "vase": ("florero", "floreros"),
    "scissors": ("tijeras", "tijeras"),
    "teddy bear": ("peluche", "peluches"),
    "hair drier": ("secadora", "secadoras"),
    "toothbrush": ("cepillo de dientes", "cepillos de dientes"),
}


def nombre(label: str, cantidad: int = 1) -> str:
    """Nombre en espanol, en singular o plural segun la cantidad."""
    singular, plural = ES.get(label, (label, label))
    return singular if abs(cantidad) == 1 else plural


def etiquetas(labels: Iterable[str]) -> Dict[str, str]:
    """Mapa {clase COCO: nombre en espanol} para enviarlo a la interfaz."""
    return {l: ES.get(l, (l, l))[0] for l in labels}


def describir(conteos: Dict[str, int], maximo: int = 6) -> str:
    """Frase con lo que hay en escena: '3 personas, 2 laptops y 1 silla'."""
    if not conteos:
        return "nada reconocible en el encuadre"
    partes = [f"{n} {nombre(clase, n)}"
              for clase, n in sorted(conteos.items(), key=lambda kv: -kv[1]) if n > 0]
    if not partes:
        return "nada reconocible en el encuadre"
    resto = len(partes) - maximo
    partes = partes[:maximo]
    frase = partes[0] if len(partes) == 1 else ", ".join(partes[:-1]) + " y " + partes[-1]
    if resto > 0:
        frase += f" y {resto} clase(s) mas"
    return frase


def catalogo() -> List[Dict[str, str]]:
    """Catalogo completo para los selectores de la interfaz."""
    return [{"clase": k, "nombre": v[0]} for k, v in ES.items()]
