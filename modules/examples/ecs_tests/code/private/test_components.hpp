#pragma once

#include "CppReflection/ReflectionProvider.hpp"
#include "CppReflection/StaticType/class.hpp"

class TestComponentA
{
public:
    int value = 42;
};

class TestComponentB
{
public:
    int value = 43;
};

class TestComponentC
{
public:
    int value = 44;
};

class TestComponentD
{
public:
    int value = 45;
};

namespace cppreflection
{

template <>
struct TypeReflectionProvider<TestComponentA>
{
    [[nodiscard]] inline constexpr static auto ReflectType()
    {
        return cppreflection::StaticClassTypeInfo<TestComponentA>(
                   "TestComponentA",
                   edt::GUID::Create("5C5ADF4B-2110-4082-AB80-1DDB629C0027"))
            .Field<"value", &TestComponentA::value>();
    }
};

template <>
struct TypeReflectionProvider<TestComponentB>
{
    [[nodiscard]] inline constexpr static auto ReflectType()
    {
        return cppreflection::StaticClassTypeInfo<TestComponentB>(
                   "TestComponentB",
                   edt::GUID::Create("453E0087-4F16-4CF3-8738-F79F4DBBAAEA"))
            .Field<"value", &TestComponentB::value>();
    }
};

template <>
struct TypeReflectionProvider<TestComponentC>
{
    [[nodiscard]] inline constexpr static auto ReflectType()
    {
        return cppreflection::StaticClassTypeInfo<TestComponentC>(
                   "TestComponentC",
                   edt::GUID::Create("0B13920E-BC1A-4C9E-A2F7-1BD4812DEF6C"))
            .Field<"value", &TestComponentC::value>();
    }
};

template <>
struct TypeReflectionProvider<TestComponentD>
{
    [[nodiscard]] inline constexpr static auto ReflectType()
    {
        return cppreflection::StaticClassTypeInfo<TestComponentD>(
                   "TestComponentD",
                   edt::GUID::Create("CBCB8923-19AD-42CB-A9C0-4C2D5FFDA1CE"))
            .Field<"value", &TestComponentD::value>();
    }
};

}  // namespace cppreflection
