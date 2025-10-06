import functools
def repeat(_func=None, *, num_times=2):
    def decorator_repeat(func):
        @functools.wraps(func)
        def wrapper_repeat(*args, **kwargs):
            for _ in range(num_times):
                value = func(*args, **kwargs)
            return value
        return wrapper_repeat

    if _func is None:
        return decorator_repeat
    else:
        return decorator_repeat(_func)
    
@repeat
def say_hi(name):
  print("in say_hi")
  return "hi "+name
@repeat(num_times=3)
def say_hi3(name):
  print("in say_hi3")
  return "hi "+name
#print(say_hi3("kyle"))

class CountCalls:
    def __init__(self, func):
        functools.update_wrapper(self, func)
        self.func = func
        self.num_calls = 0
    def __call__(self, *args, **kwargs):
        self.num_calls += 1
        print(f"Call {self.num_calls} of {self.func.__name__}()")
        return self.func(*args, **kwargs)
@CountCalls
def say_weee(name):
    print(f"{name} say weee")

say_weee("kyle")
say_weee("kyle")
say_weee("kyle")
print(say_weee.num_calls)
print(say_weee.func)
