import builtins

# 保存原始的print函数，以便在自定义print函数中可以调用
original_print = builtins.print

# 定义一个新的print函数，这个函数将覆盖原始的print
def custom_print(*args, **kwargs):
    # 在这里可以添加任何你希望执行的代码
    
    # 调用原始的print函数
    original_print(*args, **kwargs)

# 将全局的print函数替换为自定义的print函数
builtins.print = custom_print

