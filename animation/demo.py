from manim import *

class Demo(Scene):
    def construct(self):
        circle = Circle(color=BLUE).set_fill(BLUE, opacity=0.5)
        square = Square(color=ORANGE)
        title = Text("Hello Animation!").to_edge(UP)
        self.play(Write(title))
        self.play(Create(square))
        self.play(Transform(square, circle))
        self.play(square.animate.shift(RIGHT * 2).scale(0.5))
        self.wait()
